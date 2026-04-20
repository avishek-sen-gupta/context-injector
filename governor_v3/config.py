"""Configuration dataclasses for v3 machines."""

from dataclasses import dataclass, field


@dataclass
class NodeConfig:
    """A state node in the machine."""
    name: str
    initial: bool = False
    action: str | None = None
    action_params: dict = field(default_factory=dict)
    blocked_tools: list[str] = field(default_factory=list)
    allowed_exceptions: list[str] = field(default_factory=list)
    auto_transition: str | None = None


@dataclass
class EdgeConfig:
    """A transition edge in the machine."""
    from_state: str
    to_state: str
    trigger: str


@dataclass
class GateConfig:
    """A gate definition."""
    name: str
    applies_to: list[str]
    trigger: str  # "on_exit", "on_enter"
    gate_names: list[str]
    policy: str  # "strict", "soft(N)", "advisory"
    routes: dict | None = None
    params: dict = field(default_factory=dict)


@dataclass
class MachineConfig:
    """Complete machine definition."""
    name: str
    description: str
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]
    gates: list[GateConfig] = field(default_factory=list)

    def find_initial_node(self) -> NodeConfig:
        for node in self.nodes:
            if node.initial:
                return node
        raise ValueError(f"Machine {self.name} has no initial node")

    def find_edges_from(self, state_name: str) -> list[EdgeConfig]:
        return [e for e in self.edges if e.from_state == state_name]
