import pytest
from governor_v3.config import NodeConfig, EdgeConfig, GateConfig, MachineConfig

def test_node_config_creation():
    node = NodeConfig(
        name="writing_tests",
        initial=True,
        blocked_tools=["Write", "Edit"],
        allowed_exceptions=["Write(test_*)", "Edit(test_*)"],
    )
    assert node.name == "writing_tests"
    assert node.initial is True
    assert node.blocked_tools == ["Write", "Edit"]

def test_node_config_defaults():
    node = NodeConfig(name="red")
    assert node.initial is False
    assert node.action is None
    assert node.blocked_tools == []
    assert node.allowed_exceptions == []
    assert node.auto_transition is None

def test_edge_config_creation():
    edge = EdgeConfig(from_state="writing_tests", to_state="red", trigger="pytest_fail")
    assert edge.from_state == "writing_tests"
    assert edge.to_state == "red"
    assert edge.trigger == "pytest_fail"

def test_gate_config_creation():
    gate = GateConfig(
        name="test_quality",
        applies_to=["writing_tests"],
        trigger="on_exit",
        gate_names=["test_quality"],
        policy="strict",
    )
    assert gate.name == "test_quality"
    assert gate.policy == "strict"
    assert gate.routes is None

def test_machine_config_creation():
    machine = MachineConfig(
        name="tdd",
        description="TDD cycle",
        nodes=[
            NodeConfig(name="writing_tests", initial=True),
            NodeConfig(name="red", auto_transition="fixing_tests"),
        ],
        edges=[
            EdgeConfig(from_state="writing_tests", to_state="red", trigger="pytest_fail"),
        ],
    )
    assert machine.name == "tdd"
    assert len(machine.nodes) == 2
    assert len(machine.edges) == 1

def test_machine_find_initial_node():
    machine = MachineConfig(
        name="test",
        description="",
        nodes=[NodeConfig(name="start", initial=True)],
        edges=[],
    )
    assert machine.find_initial_node().name == "start"

def test_machine_find_initial_node_missing_raises():
    machine = MachineConfig(
        name="test",
        description="",
        nodes=[NodeConfig(name="start", initial=False)],
        edges=[],
    )
    with pytest.raises(ValueError, match="no initial node"):
        machine.find_initial_node()

def test_machine_find_edges_from():
    machine = MachineConfig(
        name="test",
        description="",
        nodes=[
            NodeConfig(name="a", initial=True),
            NodeConfig(name="b"),
            NodeConfig(name="c"),
        ],
        edges=[
            EdgeConfig(from_state="a", to_state="b", trigger="go"),
            EdgeConfig(from_state="a", to_state="c", trigger="skip"),
            EdgeConfig(from_state="b", to_state="c", trigger="next"),
        ],
    )
    edges_from_a = machine.find_edges_from("a")
    assert len(edges_from_a) == 2
    assert {e.trigger for e in edges_from_a} == {"go", "skip"}
