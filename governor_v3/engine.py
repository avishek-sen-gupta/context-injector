"""GovernorV3 engine: evaluate() and trigger() methods."""

import json
import os

from governor_v3.config import MachineConfig, NodeConfig, EdgeConfig, GateConfig
from governor_v3.primitives import check_tool_allowed, GATE_REGISTRY
from gates.base import GateContext, GateVerdict


class GovernorV3:
    """LangGraph-backed workflow executor."""

    def __init__(
        self,
        config: MachineConfig,
        project_root: str = ".",
        session_id: str = "default",
        state_dir: str | None = None,
    ):
        self.config = config
        self.project_root = project_root
        self.session_id = session_id
        self._state_dir = state_dir
        self._current_phase = self._load_phase() or config.find_initial_node().name

    @property
    def current_phase(self) -> str:
        return self._current_phase

    def _get_node(self, name: str | None = None) -> NodeConfig:
        target = name or self._current_phase
        for node in self.config.nodes:
            if node.name == target:
                return node
        raise ValueError(f"Node {target} not found in {self.config.name}")

    def _state_file(self) -> str | None:
        if not self._state_dir:
            return None
        return os.path.join(self._state_dir, f"{self.session_id}.json")

    def _load_phase(self) -> str | None:
        path = self._state_file()
        if not path or not os.path.exists(path):
            return None
        with open(path) as f:
            data = json.load(f)
        return data.get("current_phase")

    def _save_phase(self):
        path = self._state_file()
        if not path:
            return
        dir_path = os.path.dirname(path) or "."
        os.makedirs(dir_path, exist_ok=True)
        with open(path, "w") as f:
            json.dump({"current_phase": self._current_phase, "machine": self.config.name}, f)

    def evaluate(self, tool_name: str, tool_input: dict) -> dict:
        """Evaluate a tool call against current state. Returns action dict."""
        node = self._get_node()

        tool_arg = None
        if tool_name in ("Write", "Edit"):
            tool_arg = tool_input.get("file_path", "")
        elif tool_name == "Bash":
            tool_arg = tool_input.get("command", "")

        allowed = check_tool_allowed(
            tool_name,
            tool_arg,
            blocked=node.blocked_tools or None,
            exceptions=node.allowed_exceptions or None,
        )

        if allowed:
            return {"action": "allow", "current_phase": self._current_phase, "message": None}
        return {
            "action": "block",
            "current_phase": self._current_phase,
            "message": f"{tool_name} is blocked in {self._current_phase}",
        }

    def trigger(self, trigger_name: str) -> dict:
        """Fire a named transition with auto-advance and gate evaluation."""
        edge = self._find_edge(trigger_name)

        # Run exit gates before leaving current state
        gate_result = self._run_exit_gates(self._current_phase)
        if gate_result.get("blocked"):
            return {
                "from_state": self._current_phase,
                "to_state": self._current_phase,
                "trigger": trigger_name,
                "gate_blocked": True,
                "gate_message": gate_result.get("message", ""),
            }

        from_state = self._current_phase
        self._current_phase = edge.to_state

        # Auto-advance loop
        self._auto_advance()

        # Save state to file if state_dir is set
        self._save_phase()

        return {
            "from_state": from_state,
            "to_state": self._current_phase,
            "trigger": trigger_name,
            "auto_advanced": self._current_phase != edge.to_state,
        }

    def _find_edge(self, trigger_name: str) -> EdgeConfig:
        """Find an edge from current state with given trigger."""
        for edge in self.config.edges:
            if edge.from_state == self._current_phase and edge.trigger == trigger_name:
                return edge
        raise ValueError(f"No transition {trigger_name} from {self._current_phase}")

    def _auto_advance(self):
        """Follow auto_transition chains and on_enter gate routes."""
        visited = set()
        while True:
            if self._current_phase in visited:
                break
            visited.add(self._current_phase)

            node = self._get_node()

            # Check for on_enter gates with routes
            enter_route = self._run_enter_gates(self._current_phase)
            if enter_route:
                route_edge = self._find_edge_from(self._current_phase, enter_route)
                if route_edge:
                    self._current_phase = route_edge.to_state
                    continue

            # Check for auto_transition
            if node.auto_transition:
                auto_edge = self._find_edge_from(self._current_phase, node.auto_transition)
                if auto_edge:
                    self._current_phase = auto_edge.to_state
                    continue

            break

    def _find_edge_from(self, state: str, trigger: str):
        """Find an edge from a given state with given trigger."""
        for edge in self.config.edges:
            if edge.from_state == state and edge.trigger == trigger:
                return edge
        return None

    def _run_exit_gates(self, state_name: str) -> dict:
        """Run on_exit gates. Returns {"blocked": True, "message": ...} if strict gate fails."""
        for gate_config in self.config.gates:
            if gate_config.trigger != "on_exit" or state_name not in gate_config.applies_to:
                continue

            for gate_name in gate_config.gate_names:
                gate_cls = GATE_REGISTRY.get(gate_name)
                if not gate_cls:
                    continue
                gate = gate_cls()
                ctx = GateContext(
                    state_name=state_name,
                    transition_name="",
                    recent_tools=[],
                    recent_files=[],
                    machine=None,
                    project_root=self.project_root,
                )
                result = gate.evaluate(ctx)
                if result.verdict == GateVerdict.FAIL and gate_config.policy == "strict":
                    return {"blocked": True, "message": result.message}

        return {}

    def _run_enter_gates(self, state_name: str) -> str | None:
        """Run on_enter gates. Returns route trigger name, or None."""
        for gate_config in self.config.gates:
            if gate_config.trigger != "on_enter" or state_name not in gate_config.applies_to:
                continue
            if not gate_config.routes:
                continue

            all_pass = True
            for gate_name in gate_config.gate_names:
                gate_cls = GATE_REGISTRY.get(gate_name)
                if not gate_cls:
                    continue
                gate = gate_cls()
                ctx = GateContext(
                    state_name=state_name,
                    transition_name="",
                    recent_tools=[],
                    recent_files=[],
                    machine=None,
                    project_root=self.project_root,
                )
                result = gate.evaluate(ctx)
                if result.verdict != GateVerdict.PASS:
                    all_pass = False
                    break

            if all_pass:
                return gate_config.routes.get("pass")
            else:
                return gate_config.routes.get("fail")

        return None
