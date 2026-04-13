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
        self._audit_file = os.path.join(audit_dir, f"{session_id}.audit.json")
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

        # Check transcript for unprocessed pytest results and fire transitions.
        # This is needed because PostToolUse doesn't fire for non-zero exit codes,
        # so we detect pytest results here in PreToolUse instead.
        transcript_path = event.get("transcript_path")
        if transcript_path:
            self._check_transcript_for_pytest(transcript_path, timestamp)

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
                tool_sig = f"{tool_name}({file_path})"
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

    def trigger_transition(self, event_name: str, timestamp: str | None = None) -> dict:
        """Trigger a named transition (e.g. pytest_fail, pytest_pass).

        Called by PostToolUse hooks to drive state changes based on tool results.
        After the transition, auto-advances through any transient states.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        from_state = self.machine.current_state_name

        # Fire the transition
        send = getattr(self.machine, event_name, None)
        if send is None:
            return {
                "current_state": from_state,
                "transition": None,
                "action": "challenge",
                "message": f"Unknown transition '{event_name}'.",
                "context_to_inject": [],
            }

        try:
            send()
        except Exception:
            return {
                "current_state": from_state,
                "transition": None,
                "action": "challenge",
                "message": f"Transition '{event_name}' not valid from state '{from_state}'.",
                "context_to_inject": [],
            }

        mid_state = self.machine.current_state_name

        # Write audit for the primary transition
        audit_entry = {
            "timestamp": timestamp,
            "session_id": self.session_id,
            "machine": type(self.machine).__name__,
            "from_state": from_state,
            "to_state": mid_state,
            "trigger": "pytest_result",
            "softness": None,
            "action_taken": "allow",
            "tool_name": event_name,
            "tool_input_summary": event_name,
            "declaration": None,
            "stack_depth": 0,
            "user_prompt": False,
            "context_injected": [],
            "message": None,
        }
        write_audit_entry(self._audit_file, audit_entry)

        # Auto-advance through transient states
        context_to_inject = []
        auto_transitions = getattr(self.machine, "AUTO_TRANSITIONS", {})
        while mid_state in auto_transitions:
            auto_event = auto_transitions[mid_state]
            auto_send = getattr(self.machine, auto_event)
            prev = mid_state
            auto_send()
            mid_state = self.machine.current_state_name

            # Audit the auto-transition
            auto_audit = {
                "timestamp": timestamp,
                "session_id": self.session_id,
                "machine": type(self.machine).__name__,
                "from_state": prev,
                "to_state": mid_state,
                "trigger": "auto_transition",
                "softness": None,
                "action_taken": "allow",
                "tool_name": auto_event,
                "tool_input_summary": auto_event,
                "declaration": None,
                "stack_depth": 0,
                "user_prompt": False,
                "context_injected": [],
                "message": None,
            }
            write_audit_entry(self._audit_file, auto_audit)

        # Resolve context for the final state
        final_state = self.machine.current_state_name
        if self._last_injected_state != final_state:
            context_to_inject = self._resolve_context(final_state)
            self._last_injected_state = final_state

        # Persist final state
        self._persist_state(final_state, timestamp)
        self._recent_tools = []

        return {
            "current_state": final_state,
            "transition": f"{from_state} -> {final_state}",
            "action": "allow",
            "context_to_inject": context_to_inject,
            "message": None,
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

    def _check_transcript_for_pytest(self, transcript_path: str, timestamp: str) -> None:
        """Scan transcript for unprocessed pytest results and fire transitions.

        PostToolUse hooks don't fire for non-zero Bash exit codes, so we detect
        pytest pass/fail here by reading the transcript JSONL backwards to find
        the most recent Bash tool result containing pytest output.

        Claude Code transcript format:
        - Tool uses: type=assistant, message.content[].type=tool_use (id, name, input)
        - Tool results: type=user, message.content[].type=tool_result (tool_use_id, content)

        Uses a marker file to avoid re-processing the same result.
        """
        if not os.path.exists(transcript_path):
            return

        marker_file = os.path.join(self.state_dir, f"{self.project_hash}.last_pytest_line")
        last_processed_line = 0
        if os.path.exists(marker_file):
            try:
                last_processed_line = int(open(marker_file).read().strip())
            except (ValueError, OSError):
                pass

        try:
            with open(transcript_path) as f:
                lines = f.readlines()
        except OSError:
            return

        # First pass: index tool_use blocks by id → command
        # so we can look up whether a tool_result's corresponding call was pytest
        tool_use_commands: dict[str, str] = {}
        for line in lines:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, IndexError):
                continue
            if entry.get("type") != "assistant":
                continue
            for block in entry.get("message", {}).get("content", []):
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Bash"
                ):
                    cmd = block.get("input", {}).get("command", "")
                    tool_use_commands[block.get("id", "")] = cmd

        # Scan backwards for the most recent tool_result that corresponds to a pytest call
        for line_num in range(len(lines) - 1, -1, -1):
            if line_num <= last_processed_line:
                break
            try:
                entry = json.loads(lines[line_num])
            except (json.JSONDecodeError, IndexError):
                continue

            # Tool results live inside "user" entries → message.content[]
            if entry.get("type") != "user":
                continue

            for block in entry.get("message", {}).get("content", []):
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue

                tool_use_id = block.get("tool_use_id", "")
                cmd = tool_use_commands.get(tool_use_id, "")
                if not re.search(r'\bpytest\b', cmd):
                    continue

                # Extract output text from the tool_result content
                content = block.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") for c in content if isinstance(c, dict)
                    )
                if not isinstance(content, str):
                    continue

                # Determine pass/fail
                event_name = None
                if re.search(r'(FAILED|ERROR|failed|error.*occurred)', content):
                    event_name = "pytest_fail"
                elif re.search(r'(passed|no tests ran)', content):
                    event_name = "pytest_pass"

                if event_name:
                    # Mark as processed
                    try:
                        with open(marker_file, "w") as f:
                            f.write(str(line_num))
                    except OSError:
                        pass

                    # Fire the transition and auto-advance
                    send = getattr(self.machine, event_name, None)
                    if send:
                        try:
                            send()
                            auto_transitions = getattr(self.machine, "AUTO_TRANSITIONS", {})
                            mid_state = self.machine.current_state_name
                            while mid_state in auto_transitions:
                                auto_event = auto_transitions[mid_state]
                                auto_send = getattr(self.machine, auto_event)
                                auto_send()
                                mid_state = self.machine.current_state_name
                            self._persist_state(mid_state, timestamp)
                            self._recent_tools = []
                        except Exception:
                            pass
                return  # Only process the most recent pytest result

    def _check_preconditions(self, required_patterns: list[str]) -> bool:
        """Check if any recent tool use matches at least one required pattern."""
        for tool_sig in self._recent_tools:
            # Create basename version for pattern matching
            # e.g. Write(/project/tests/test_foo.py) -> Write(test_foo.py)
            basename_sig = tool_sig
            if "(" in tool_sig and not tool_sig.startswith("Bash("):
                name, inner = tool_sig.split("(", 1)
                inner = inner.rstrip(")")
                basename_sig = f"{name}({os.path.basename(inner)})"
            for pattern in required_patterns:
                if fnmatch.fnmatch(tool_sig, pattern) or fnmatch.fnmatch(basename_sig, pattern):
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
        """Check if a tool use is allowed in the current state.

        Uses BLOCKED_TOOLS (blocklist) if defined, else falls back to ALLOWED_TOOLS (allowlist).
        Blocklist is preferred: everything is allowed unless explicitly blocked.
        """
        state_name = self.machine.current_state_name
        file_path = tool_input.get("file_path", tool_input.get("command", ""))
        target = os.path.basename(file_path)
        tool_with_target = f"{tool_name}({target})"

        # Blocklist mode: block matching tools, allow everything else.
        # Patterns prefixed with ! are exceptions (allowlist overrides).
        blocked = self.machine.get_blocked_tools(state_name)
        if blocked is not None:
            exceptions = [p[1:] for p in blocked if p.startswith("!")]
            block_patterns = [p for p in blocked if not p.startswith("!")]

            # Check exceptions first — if tool matches an exception, allow it
            for pattern in exceptions:
                if self._matches_tool_pattern(tool_name, target, tool_with_target, pattern):
                    return "allow", None

            # Check block patterns
            for pattern in block_patterns:
                if self._matches_tool_pattern(tool_name, target, tool_with_target, pattern):
                    return (
                        "challenge",
                        f"Tool '{tool_name}' targeting '{target}' is blocked in state "
                        f"'{state_name}'. Run pytest to transition to the correct phase.",
                    )
            return "allow", None

        # Allowlist mode (legacy): only listed tools are allowed
        allowed = self.machine.get_allowed_tools(state_name)
        if allowed is None or allowed == ["*"]:
            return "allow", None

        for pattern in allowed:
            if self._matches_tool_pattern(tool_name, target, tool_with_target, pattern):
                return "allow", None

        return (
            "challenge",
            f"Tool '{tool_name}' targeting '{target}' is not in the "
            f"allowed list for state '{state_name}': {allowed}. "
            f"Declare a phase transition if you need to do this.",
        )

    @staticmethod
    def _matches_tool_pattern(
        tool_name: str, target: str, tool_with_target: str, pattern: str
    ) -> bool:
        """Check if a tool call matches a pattern like 'Write', 'Write(test_*)', etc."""
        if fnmatch.fnmatch(tool_with_target, pattern):
            return True
        pat_name = pattern.split("(")[0] if "(" in pattern else pattern
        if fnmatch.fnmatch(tool_name, pat_name):
            if "(" in pattern:
                inner = pattern.split("(", 1)[1].rstrip(")")
                return fnmatch.fnmatch(target, inner)
            return True
        return False

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


def _build_governor(event: dict) -> "Governor":
    """Build a Governor instance from environment variables and event data."""
    state_dir = os.environ.get("CTX_STATE_DIR", "/tmp/ctx-state")
    audit_dir = os.environ.get("CTX_AUDIT_DIR", os.path.join(os.getcwd(), ".claude", "audit"))
    context_dir = os.environ.get("CTX_CONTEXT_DIR", os.path.join(os.getcwd(), ".claude"))
    project_hash = os.environ.get("CTX_PROJECT_HASH", "default")
    session_id = event.get("session_id", "unknown")
    machine_module = os.environ.get("CTX_MACHINE", "machines.tdd.TDD")

    # Dynamic machine loading
    module_path, class_name = machine_module.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    machine_cls = getattr(mod, class_name)

    return Governor(
        machine=machine_cls(),
        state_dir=state_dir,
        audit_dir=audit_dir,
        context_dir=context_dir,
        project_hash=project_hash,
        session_id=session_id,
    )


def _print_status():
    """Print the current governor status as JSON."""
    import hashlib

    state_dir = os.environ.get("CTX_STATE_DIR", "/tmp/ctx-state")
    project_hash = os.environ.get(
        "CTX_PROJECT_HASH",
        hashlib.md5(os.getcwd().encode()).hexdigest(),
    )
    governor_dir = os.environ.get("CTX_GOVERNOR_DIR", "/tmp/ctx-governor")
    governor_lock = os.path.join(governor_dir, project_hash)

    if not os.path.exists(governor_lock):
        json.dump({"active": False}, sys.stdout, indent=2)
        print()
        return

    machine_file = os.path.join(state_dir, f"{project_hash}.machine")
    state_file = os.path.join(state_dir, f"{project_hash}.json")

    machine_name = None
    if os.path.exists(machine_file):
        machine_name = open(machine_file).read().strip()

    current_state = None
    session_id = None
    last_injection = None
    if os.path.exists(state_file):
        state = load_state(state_file)
        current_state = state.get("inner_state")
        session_id = state.get("session_id")
        last_injection = state.get("last_injection_timestamp")

    status = {
        "active": True,
        "machine": machine_name,
        "state": current_state,
        "session_id": session_id,
        "last_injection": last_injection,
    }
    json.dump(status, sys.stdout, indent=2)
    print()


def _print_context():
    """Print resolved context file paths for the current state, one per line."""
    import importlib

    state_dir = os.environ.get("CTX_STATE_DIR", "/tmp/ctx-state")
    context_dir = os.environ.get("CTX_CONTEXT_DIR", os.path.join(os.getcwd(), ".claude"))
    project_hash = os.environ.get("CTX_PROJECT_HASH", "default")

    state_file = os.path.join(state_dir, f"{project_hash}.json")
    machine_file = os.path.join(state_dir, f"{project_hash}.machine")

    if not os.path.exists(state_file):
        return

    state = load_state(state_file)
    inner_state = state.get("inner_state")
    if not inner_state:
        return

    machine_module = "machines.tdd.TDD"
    if os.path.exists(machine_file):
        machine_module = open(machine_file).read().strip()

    module_path, class_name = machine_module.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    machine_cls = getattr(mod, class_name)
    machine = machine_cls()

    patterns = machine.get_context(inner_state)
    import glob as globmod
    for pattern in patterns:
        full_pattern = os.path.join(context_dir, pattern)
        if "*" in pattern:
            for path in sorted(globmod.glob(full_pattern)):
                print(path)
        else:
            full_path = os.path.join(context_dir, pattern)
            if os.path.exists(full_path):
                print(full_path)


def main():
    """CLI entry point: read JSON from stdin, write response to stdout.

    Modes:
      - Default (no args): evaluate a PreToolUse event
      - 'trigger <event_name>': fire a named transition (e.g. pytest_fail)
      - 'status': print current governor state
      - 'context': print resolved context file paths for current state
    """
    if len(sys.argv) >= 2 and sys.argv[1] == "status":
        _print_status()
        return
    elif len(sys.argv) >= 2 and sys.argv[1] == "context":
        _print_context()
        return
    elif len(sys.argv) >= 2 and sys.argv[1] == "session-instructions":
        event = json.load(sys.stdin)
        gov = _build_governor(event)
        print(gov.machine.SESSION_INSTRUCTIONS)
        return
    elif len(sys.argv) >= 3 and sys.argv[1] == "trigger":
        event_name = sys.argv[2]
        event = json.load(sys.stdin)
        gov = _build_governor(event)
        result = gov.trigger_transition(event_name)
    else:
        event = json.load(sys.stdin)
        gov = _build_governor(event)
        result = gov.evaluate(event)

    json.dump(result, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
