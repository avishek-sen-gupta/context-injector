# tests/test_v4_tdd_config.py
import os
import pytest
from governor_v4.loader import load_machine_from_json

TDD_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")


def test_load_tdd_machine():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert config.name == "tdd"


def test_tdd_has_four_states():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    names = {n.name for n in config.nodes}
    assert names == {"writing_tests", "fixing_tests", "refactoring", "fixing_lint"}


def test_tdd_initial_is_writing_tests():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert config.find_initial_node().name == "writing_tests"


def test_tdd_has_seven_edges():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert len(config.edges) == 7


def test_tdd_writing_tests_blocks_write():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    node = next(n for n in config.nodes if n.name == "writing_tests")
    assert "Write" in node.blocked_tools
    assert "Edit" in node.blocked_tools
    assert "Write(test_*)" in node.allowed_exceptions


def test_tdd_writing_tests_captures_pytest():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    node = next(n for n in config.nodes if n.name == "writing_tests")
    assert len(node.capture) == 1
    assert node.capture[0].tool_pattern == "Bash(*pytest*)"
    assert node.capture[0].evidence_type == "pytest_output"


def test_tdd_fixing_tests_captures_pytest_and_lint():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    node = next(n for n in config.nodes if n.name == "fixing_tests")
    types = {c.evidence_type for c in node.capture}
    assert types == {"pytest_output", "lint_output"}


def test_tdd_edge_writing_to_fixing_has_contract():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    edge = config.find_edge("writing_tests", "fixing_tests")
    assert edge is not None
    assert edge.evidence_contract.required_type == "pytest_output"
    assert edge.evidence_contract.gate == "pytest_fail_gate"


def test_tdd_edge_fixing_to_writing_no_contract():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    edge = config.find_edge("fixing_tests", "writing_tests")
    assert edge is not None
    assert edge.evidence_contract is None


def test_tdd_edge_refactoring_to_fixing_lint_has_contract():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    edge = config.find_edge("refactoring", "fixing_lint")
    assert edge is not None
    assert edge.evidence_contract.required_type == "lint_output"
    assert edge.evidence_contract.gate == "lint_fail_gate"
