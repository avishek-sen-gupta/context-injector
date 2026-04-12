"""Governor process for state machine-governed context injection.

Evaluates tool events against the active state machine. Determines transitions,
applies graduated response based on softness, injects context, and writes audit.

Contract: reads JSON from stdin, writes JSON to stdout.
When used as a library, call Governor.evaluate(event_dict) directly.
"""

import fnmatch
import json
import os
import re
import sys
from datetime import datetime, timezone

from governor.audit import write_audit_entry
from governor.state_io import load_state, save_state


# Graduated response thresholds
SOFTNESS_ALLOW = 0.7
SOFTNESS_REMIND = 0.3


class Governor:
    """Evaluates tool events against a governed state machine."""

    def __init__(
        self,
        machine,
        state_dir: str,
        audit_dir: str,
        context_dir: str,
        project_hash: str,
        session_id: str,
    ):
        self.machine = machine
        self.state_dir = state_dir
        self.audit_dir = audit_dir
        self.context_dir = context_dir
        self.project_hash = project_hash
        self.session_id = session_id

        self._state_file = os.path.join(state_dir, f"{project_hash}.json")
        self._audit_file = os.path.join(audit_dir, f"{session_id}.jsonl")
        self._last_injected_state = None

        # Load persisted state and restore machine position
        persisted = load_state(self._state_file, session_id=session_id)
        saved_state = persisted.get("inner_state")
        if saved_state and saved_state != self.machine.current_state_name:
            self._restore_machine_state(saved_state)
        self._last_injected_state = persisted.get("last_injected_state")
        self._recent_tools: list[str] = persisted.get("recent_tools", [])

    def _restore_machine_state(self, target_state: str) -> None:
        """Attempt to restore machine to a previously persisted state.

        USE V3 API: set current_state_value directly, NOT _current_state.
        Verify target_state is valid by checking states_map.
        """
        if target_state in self.machine.states_map:
            self.machine.current_state_value = target_state

    def evaluate(self, event: dict) -> dict:
        """Evaluate a single event and return the governor response."""
        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input", {})
        timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

        from_state = self.machine.current_state_name

        # Check for DeclarePhase pattern
        declaration = self._extract_declaration(tool_name, tool_input)

        transition_name = None
        softness = None
        action = "allow"
        message = None
        context_to_inject = []

        if declaration:
            transition_name, softness, action, message = self._handle_declaration(
                declaration
            )
        else:
            # Track this tool use for precondition checking
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                tool_sig = f"Bash({command})"
            else:
                file_path = tool_input.get("file_path", "")
                tool_sig = f"{tool_name}({os.path.basename(file_path)})"
            self._recent_tools.append(tool_sig)

            action, message = self._check_tool_against_state(tool_name, tool_input)

        to_state = self.machine.current_state_name
        transitioned = from_state != to_state

        # Context injection: only when state changed or first evaluation
        if transitioned or self._last_injected_state != to_state:
            context_to_inject = self._resolve_context(to_state)
            self._last_injected_state = to_state

        # Persist state
        self._persist_state(to_state, timestamp)

        # Build audit entry
        audit_entry = {
            "timestamp": timestamp,
            "session_id": self.session_id,
            "machine": type(self.machine).__name__,
            "from_state": from_state,
            "to_state": to_state if transitioned else None,
            "trigger": "declaration" if declaration else "tool_use",
            "softness": softness,
            "action_taken": action,
            "tool_name": tool_name,
            "tool_input_summary": self._summarize_tool_input(tool_input),
            "declaration": declaration.get("reason") if declaration else None,
            "stack_depth": 0,
            "user_prompt": False,
            "context_injected": context_to_inject,
            "message": message,
        }
        write_audit_entry(self._audit_file, audit_entry)

        transition_str = None
        if transitioned:
            transition_str = f"{from_state} -> {to_state}"

        return {
            "current_state": to_state,
            "transition": transition_str,
            "softness": softness,
            "action": action,
            "context_to_inject": context_to_inject,
            "message": message,
            "audit_entry": audit_entry,
        }

    def _extract_declaration(self, tool_name: str, tool_input: dict) -> dict | None:
        """Extract a DeclarePhase declaration from a Bash echo command."""
        if tool_name != "Bash":
            return None
        command = tool_input.get("command", "")
        match = re.search(r"""echo\s+'(\{"declare_phase".*?\})'""", command)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    def _handle_declaration(self, declaration: dict) -> tuple:
        """Process a phase declaration. Returns (transition_name, softness, action, message).

        IMPORTANT: Use v3 API - states_map[current_state_value] to get State object.
        """
        target_phase = declaration.get("declare_phase", "")

        # Get the current State object via v3 API
        current = self.machine.states_map[self.machine.current_state_value]

        # Find a transition from current state to the target phase
        for transition in current.transitions:
            if transition.source != current:
                continue
            if transition.target.id == target_phase:
                transition_name = transition.event

                # Check preconditions before allowing the transition
                preconditions = self.machine.get_preconditions(transition_name)
                if preconditions and not self._check_preconditions(preconditions):
                    return (
                        transition_name,
                        0.0,
                        "challenge",
                        f"Precondition not met for '{transition_name}': expected one of "
                        f"{preconditions} in recent tool usage, but none found. "
                        f"Complete the required work before declaring this transition.",
                    )

                softness = self.machine.get_softness(transition_name)
                action, message = self._graduated_response(softness, transition_name, target_phase)

                # Execute the transition if allowed, reset recent tools
                if action in ("allow", "remind"):
                    send = getattr(self.machine, transition_name)
                    send()
                    self._recent_tools = []

                return transition_name, softness, action, message

        # No valid transition found
        return (
            None,
            None,
            "challenge",
            f"No valid transition from '{self.machine.current_state_name}' to '{target_phase}'. "
            f"Available transitions: {', '.join(self.machine.available_transition_names)}.",
        )

    def _check_preconditions(self, required_patterns: list[str]) -> bool:
        """Check if any recent tool use matches at least one required pattern."""
        for tool_sig in self._recent_tools:
            for pattern in required_patterns:
                if fnmatch.fnmatch(tool_sig, pattern):
                    return True
        return False

    def _graduated_response(
        self, softness: float, transition_name: str, target_phase: str
    ) -> tuple[str, str | None]:
        """Apply graduated response bands based on softness."""
        if softness >= SOFTNESS_ALLOW:
            return "allow", None
        elif softness >= SOFTNESS_REMIND:
            return (
                "remind",
                f"Deviation: transitioning to '{target_phase}' via '{transition_name}' "
                f"(softness {softness}). This is outside the expected flow.",
            )
        else:
            return (
                "challenge",
                f"Low-confidence transition to '{target_phase}' via '{transition_name}' "
                f"(softness {softness}). Justify this deviation or return to the expected flow.",
            )

    def _check_tool_against_state(
        self, tool_name: str, tool_input: dict
    ) -> tuple[str, str | None]:
        """Check if a tool use is allowed in the current state."""
        allowed = self.machine.get_allowed_tools(self.machine.current_state_name)
        if allowed is None or allowed == ["*"]:
            return "allow", None

        file_path = tool_input.get("file_path", tool_input.get("command", ""))
        tool_with_target = f"{tool_name}({os.path.basename(file_path)})"

        for pattern in allowed:
            if fnmatch.fnmatch(tool_with_target, pattern):
                return "allow", None
            if fnmatch.fnmatch(tool_name, pattern.split("(")[0] if "(" in pattern else pattern):
                # Tool name matches but target might not — check target pattern
                if "(" in pattern:
                    inner = pattern.split("(", 1)[1].rstrip(")")
                    if fnmatch.fnmatch(os.path.basename(file_path), inner):
                        return "allow", None
                else:
                    return "allow", None

        return (
            "challenge",
            f"Tool '{tool_name}' targeting '{os.path.basename(file_path)}' is not in the "
            f"allowed list for state '{self.machine.current_state_name}': {allowed}. "
            f"Declare a phase transition if you need to do this.",
        )

    def _resolve_context(self, state_name: str) -> list[str]:
        """Resolve context file patterns to actual file paths."""
        patterns = self.machine.get_context(state_name)
        resolved = []
        for pattern in patterns:
            full_pattern = os.path.join(self.context_dir, pattern)
            if "*" in pattern:
                import glob
                resolved.extend(sorted(glob.glob(full_pattern)))
            else:
                full_path = os.path.join(self.context_dir, pattern)
                if os.path.exists(full_path):
                    resolved.append(full_path)
        return resolved

    def _persist_state(self, current_state: str, timestamp: str) -> None:
        """Write the current state to the state file."""
        state = {
            "outer_machine": None,
            "outer_state": None,
            "inner_machine": type(self.machine).__name__,
            "inner_state": current_state,
            "stack": [],
            "last_injected_state": self._last_injected_state,
            "last_injection_timestamp": timestamp,
            "session_id": self.session_id,
            "recent_tools": self._recent_tools,
        }
        save_state(self._state_file, state)

    def _summarize_tool_input(self, tool_input: dict) -> str:
        """Create a short summary of tool input for the audit log."""
        if "file_path" in tool_input:
            return tool_input["file_path"]
        if "command" in tool_input:
            cmd = tool_input["command"]
            return cmd[:100] + "..." if len(cmd) > 100 else cmd
        return json.dumps(tool_input)[:100]


def main():
    """CLI entry point: read JSON from stdin, write response to stdout."""
    event = json.load(sys.stdin)

    state_dir = os.environ.get("CTX_STATE_DIR", "/tmp/ctx-state")
    audit_dir = os.environ.get("CTX_AUDIT_DIR", os.path.join(os.getcwd(), ".claude", "audit"))
    context_dir = os.environ.get("CTX_CONTEXT_DIR", os.path.join(os.getcwd(), ".claude"))
    project_hash = os.environ.get("CTX_PROJECT_HASH", "default")
    session_id = event.get("session_id", "unknown")
    machine_module = os.environ.get("CTX_MACHINE", "machines.tdd_cycle.TDDCycle")

    # Dynamic machine loading
    module_path, class_name = machine_module.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    machine_cls = getattr(mod, class_name)

    gov = Governor(
        machine=machine_cls(),
        state_dir=state_dir,
        audit_dir=audit_dir,
        context_dir=context_dir,
        project_hash=project_hash,
        session_id=session_id,
    )

    result = gov.evaluate(event)
    json.dump(result, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
