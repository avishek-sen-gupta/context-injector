"""Configuration dataclasses for v4 machines."""

from dataclasses import dataclass, field


@dataclass
class CaptureRule:
    """Defines which tool outputs to capture as evidence."""

    tool_pattern: str  # e.g. "Bash(*pytest*)"
    evidence_type: str  # e.g. "pytest_output"


@dataclass
class EvidenceContract:
    """Defines what evidence an edge requires for transition."""

    required_type: str  # must match CaptureRule.evidence_type
    gate: str  # gate name from GATE_REGISTRY


@dataclass
class NodeConfig:
    """A state node in the machine."""

    name: str
    initial: bool = False
    blocked_tools: list[str] = field(default_factory=list)
    allowed_exceptions: list[str] = field(default_factory=list)
    capture: list[CaptureRule] = field(default_factory=list)


@dataclass
class EdgeConfig:
    """A transition edge identified by from/to states."""

    from_state: str
    to_state: str
    evidence_contract: EvidenceContract | None = None


@dataclass
class MachineConfig:
    """Complete machine definition."""

    name: str
    description: str
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]

    def find_initial_node(self) -> NodeConfig:
        for node in self.nodes:
            if node.initial:
                return node
        raise ValueError(f"Machine {self.name} has no initial node")

    def find_edge(self, from_state: str, to_state: str) -> EdgeConfig | None:
        for edge in self.edges:
            if edge.from_state == from_state and edge.to_state == to_state:
                return edge
        return None
