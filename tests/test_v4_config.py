import pytest
from governor_v4.config import (
    CaptureRule, EvidenceContract, NodeConfig, EdgeConfig, MachineConfig,
)


class TestCaptureRule:
    def test_creation(self):
        rule = CaptureRule(tool_pattern="Bash(pytest*)", evidence_type="pytest_output")
        assert rule.tool_pattern == "Bash(pytest*)"
        assert rule.evidence_type == "pytest_output"


class TestEvidenceContract:
    def test_creation(self):
        contract = EvidenceContract(required_type="pytest_output", gate="pytest_fail_gate")
        assert contract.required_type == "pytest_output"
        assert contract.gate == "pytest_fail_gate"


class TestNodeConfig:
    def test_creation_with_capture(self):
        node = NodeConfig(
            name="writing_tests",
            initial=True,
            blocked_tools=["Write", "Edit"],
            allowed_exceptions=["Write(test_*)", "Edit(test_*)"],
            capture=[CaptureRule(tool_pattern="Bash(pytest*)", evidence_type="pytest_output")],
        )
        assert node.name == "writing_tests"
        assert node.initial is True
        assert len(node.capture) == 1
        assert node.capture[0].evidence_type == "pytest_output"

    def test_defaults(self):
        node = NodeConfig(name="idle")
        assert node.initial is False
        assert node.blocked_tools == []
        assert node.allowed_exceptions == []
        assert node.capture == []


class TestEdgeConfig:
    def test_with_contract(self):
        edge = EdgeConfig(
            from_state="writing_tests",
            to_state="fixing_tests",
            evidence_contract=EvidenceContract(required_type="pytest_output", gate="pytest_fail_gate"),
        )
        assert edge.from_state == "writing_tests"
        assert edge.to_state == "fixing_tests"
        assert edge.evidence_contract.gate == "pytest_fail_gate"

    def test_without_contract(self):
        edge = EdgeConfig(from_state="fixing_tests", to_state="writing_tests")
        assert edge.evidence_contract is None


class TestMachineConfig:
    def test_creation(self):
        machine = MachineConfig(
            name="tdd",
            description="TDD cycle",
            nodes=[
                NodeConfig(name="writing_tests", initial=True),
                NodeConfig(name="fixing_tests"),
            ],
            edges=[
                EdgeConfig(from_state="writing_tests", to_state="fixing_tests"),
            ],
        )
        assert machine.name == "tdd"
        assert len(machine.nodes) == 2
        assert len(machine.edges) == 1

    def test_find_initial_node(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="start", initial=True)],
            edges=[],
        )
        assert machine.find_initial_node().name == "start"

    def test_find_initial_node_missing_raises(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="start")],
            edges=[],
        )
        with pytest.raises(ValueError, match="no initial node"):
            machine.find_initial_node()

    def test_find_edge(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="a", initial=True), NodeConfig(name="b")],
            edges=[EdgeConfig(from_state="a", to_state="b")],
        )
        edge = machine.find_edge("a", "b")
        assert edge is not None
        assert edge.to_state == "b"

    def test_find_edge_missing_returns_none(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="a", initial=True), NodeConfig(name="b")],
            edges=[],
        )
        assert machine.find_edge("a", "b") is None
