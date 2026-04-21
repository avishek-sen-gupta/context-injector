"""GovernorV4 engine: evaluate() and want_to_transition()."""

import json
import os

from governor_v4.config import MachineConfig, NodeConfig
from governor_v4.locker import EvidenceLocker
from governor_v4.primitives import check_tool_allowed
from governor_v4.gates import GATE_REGISTRY, GateVerdict


class GovernorV4:
    """Evidence-based workflow engine.

    The agent decides when to transition and provides evidence.
    The governor validates evidence against edge contracts via gates.
    """

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
        self._locker = EvidenceLocker(state_dir, session_id) if state_dir else None
        self._current_phase = self._load_phase() or config.find_initial_node().name

    @property
    def current_phase(self) -> str:
        return self._current_phase

    @property
    def locker(self) -> EvidenceLocker | None:
        return self._locker

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
            json.dump(
                {"current_phase": self._current_phase, "machine": self.config.name}, f
            )

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
            return {
                "action": "allow",
                "current_phase": self._current_phase,
                "message": None,
            }
        return {
            "action": "block",
            "current_phase": self._current_phase,
            "message": f"{tool_name} is blocked in {self._current_phase}",
        }

    def want_to_transition(
        self, target_state: str, evidence_key: str | None = None
    ) -> dict:
        """Request a state transition with optional evidence.

        1. Find edge from current_state to target_state
        2. If edge has evidence_contract: validate evidence via gate
        3. Transition or deny
        """
        # 1. Find edge
        edge = self.config.find_edge(self._current_phase, target_state)
        if not edge:
            return {
                "action": "deny",
                "current_phase": self._current_phase,
                "message": f"No edge from {self._current_phase} to {target_state}",
            }

        # 2. Check evidence contract
        if edge.evidence_contract:
            if not evidence_key:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": f"Transition to {target_state} requires evidence",
                }

            if not self._locker:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": "No evidence locker configured",
                }

            entry = self._locker.retrieve(evidence_key)
            if not entry:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": f"Evidence key {evidence_key} not found in locker",
                }

            if entry.get("type") != edge.evidence_contract.required_type:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": (
                        f"Evidence type {entry.get('type')} does not match "
                        f"required {edge.evidence_contract.required_type}"
                    ),
                }

            # 3. Run gate
            gate_cls = GATE_REGISTRY.get(edge.evidence_contract.gate)
            if not gate_cls:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": f"Gate {edge.evidence_contract.gate} not found in registry",
                }
            gate = gate_cls()
            result = gate.validate([evidence_key], self._locker)
            if result.verdict == GateVerdict.FAIL:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": result.message
                    or f"Gate {edge.evidence_contract.gate} denied transition",
                }

        # 4. Transition
        from_state = self._current_phase
        self._current_phase = target_state
        self._save_phase()

        return {
            "action": "allow",
            "from_state": from_state,
            "to_state": target_state,
            "current_phase": self._current_phase,
            "message": None,
        }
