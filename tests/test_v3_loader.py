import json
import tempfile
import pytest
from governor_v3.loader import load_machine_from_json
from governor_v3.config import MachineConfig

SIMPLE_MACHINE = """{
    "name": "tdd",
    "description": "TDD cycle",
    "nodes": [
        {
            "name": "writing_tests",
            "initial": true,
            "blocked_tools": ["Write", "Edit"],
            "allowed_exceptions": ["Write(test_*)", "Edit(test_*)"]
        },
        {
            "name": "red",
            "auto_transition": "fixing_tests"
        }
    ],
    "edges": [
        {"from": "writing_tests", "to": "red", "trigger": "pytest_fail"}
    ]
}"""

def test_load_machine_from_json_string():
    config = load_machine_from_json(SIMPLE_MACHINE)
    assert isinstance(config, MachineConfig)
    assert config.name == "tdd"
    assert len(config.nodes) == 2
    assert len(config.edges) == 1

def test_load_machine_from_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(SIMPLE_MACHINE)
        f.flush()
        config = load_machine_from_json(f.name, from_file=True)
        assert config.name == "tdd"

def test_load_validates_no_duplicate_nodes():
    bad = json.dumps({
        "name": "bad", "description": "",
        "nodes": [{"name": "a", "initial": True}, {"name": "a"}],
        "edges": [],
    })
    with pytest.raises(ValueError, match="duplicate node"):
        load_machine_from_json(bad)

def test_load_validates_edge_references():
    bad = json.dumps({
        "name": "bad", "description": "",
        "nodes": [{"name": "a", "initial": True}],
        "edges": [{"from": "a", "to": "nonexistent", "trigger": "x"}],
    })
    with pytest.raises(ValueError, match="nonexistent"):
        load_machine_from_json(bad)

def test_load_machine_with_gates():
    src = json.dumps({
        "name": "tdd", "description": "",
        "nodes": [{"name": "writing_tests", "initial": True}],
        "edges": [],
        "gates": [{
            "name": "test_quality",
            "applies_to": ["writing_tests"],
            "trigger": "on_exit",
            "gate_names": ["test_quality"],
            "policy": "strict",
        }],
    })
    config = load_machine_from_json(src)
    assert len(config.gates) == 1
    assert config.gates[0].name == "test_quality"

def test_load_node_defaults():
    src = json.dumps({
        "name": "minimal", "description": "",
        "nodes": [{"name": "start", "initial": True}],
        "edges": [],
    })
    config = load_machine_from_json(src)
    node = config.nodes[0]
    assert node.blocked_tools == []
    assert node.allowed_exceptions == []
    assert node.action is None
    assert node.auto_transition is None
