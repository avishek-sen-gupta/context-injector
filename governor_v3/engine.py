"""GovernorV3 engine: evaluate() and trigger() methods."""

from governor_v3.config import MachineConfig, NodeConfig
from governor_v3.primitives import check_tool_allowed


class GovernorV3:
    """LangGraph-backed workflow executor."""

    def __init__(
        self,
        config: MachineConfig,
        project_root: str = ".",
        session_id: str = "default",
    ):
        self.config = config
        self.project_root = project_root
        self.session_id = session_id
        self._current_phase = config.find_initial_node().name

    @property
    def current_phase(self) -> str:
        return self._current_phase

    def _get_node(self, name: str | None = None) -> NodeConfig:
        target = name or self._current_phase
        for node in self.config.nodes:
            if node.name == target:
                return node
        raise ValueError(f"Node {target} not found in {self.config.name}")

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
        """Fire a named transition. Stub — replaced in Task 6."""
        for edge in self.config.edges:
            if edge.from_state == self._current_phase and edge.trigger == trigger_name:
                from_state = self._current_phase
                self._current_phase = edge.to_state
                return {"from_state": from_state, "to_state": edge.to_state, "trigger": trigger_name}
        raise ValueError(f"No transition {trigger_name} from {self._current_phase}")
