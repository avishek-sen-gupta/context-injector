# tests/test_v4_loader.py
import json
import tempfile
import pytest
from governor_v4.loader import load_machine_from_json
from governor_v4.config import MachineConfig

SIMPLE_MACHINE = json.dumps({
    "name": "tdd",
    "description": "TDD cycle",
    "nodes": [
        {
            "name": "writing_tests",
            "initial": True,
            "blocked_tools": ["Write", "Edit"],
            "allowed_exceptions": ["Write(test_*)", "Edit(test_*)"],
            "capture": [
                {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"}
            ],
        },
        {"name": "fixing_tests"},
    ],
    "edges": [
        {
            "from": "writing_tests", "to": "fixing_tests",
            "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_fail_gate"},
        },
        {"from": "fixing_tests", "to": "writing_tests"},
    ],
})


class TestLoadFromString:
    def test_load_basic(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        assert isinstance(config, MachineConfig)
        assert config.name == "tdd"
        assert len(config.nodes) == 2
        assert len(config.edges) == 2

    def test_node_capture_rules(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        wt = next(n for n in config.nodes if n.name == "writing_tests")
        assert len(wt.capture) == 1
        assert wt.capture[0].tool_pattern == "Bash(pytest*)"
        assert wt.capture[0].evidence_type == "pytest_output"

    def test_edge_with_contract(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        edge = config.find_edge("writing_tests", "fixing_tests")
        assert edge.evidence_contract is not None
        assert edge.evidence_contract.required_type == "pytest_output"
        assert edge.evidence_contract.gate == "pytest_fail_gate"

    def test_edge_without_contract(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        edge = config.find_edge("fixing_tests", "writing_tests")
        assert edge.evidence_contract is None

    def test_node_defaults(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        ft = next(n for n in config.nodes if n.name == "fixing_tests")
        assert ft.blocked_tools == []
        assert ft.allowed_exceptions == []
        assert ft.capture == []


class TestLoadFromFile:
    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(SIMPLE_MACHINE)
            f.flush()
            config = load_machine_from_json(f.name, from_file=True)
            assert config.name == "tdd"


class TestValidation:
    def test_duplicate_nodes(self):
        bad = json.dumps({
            "name": "bad", "description": "",
            "nodes": [{"name": "a", "initial": True}, {"name": "a"}],
            "edges": [],
        })
        with pytest.raises(ValueError, match="duplicate node"):
            load_machine_from_json(bad)

    def test_edge_references_nonexistent_node(self):
        bad = json.dumps({
            "name": "bad", "description": "",
            "nodes": [{"name": "a", "initial": True}],
            "edges": [{"from": "a", "to": "nonexistent"}],
        })
        with pytest.raises(ValueError, match="nonexistent"):
            load_machine_from_json(bad)
