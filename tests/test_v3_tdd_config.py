import os
import pytest
from governor_v3.loader import load_machine_from_json

TDD_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd.json")

def test_load_tdd_machine():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert config.name == "tdd"

def test_tdd_has_six_states():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    names = {n.name for n in config.nodes}
    assert names == {"writing_tests", "red", "fixing_tests", "green", "linting", "fixing_lint"}

def test_tdd_initial_is_writing_tests():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert config.find_initial_node().name == "writing_tests"

def test_tdd_has_expected_triggers():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    triggers = {e.trigger for e in config.edges}
    assert triggers == {
        "pytest_fail", "pytest_pass", "start_fixing", "start_linting",
        "add_tests", "lint_pass", "lint_fail",
    }

def test_tdd_writing_tests_blocks_write():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    node = next(n for n in config.nodes if n.name == "writing_tests")
    assert "Write" in node.blocked_tools
    assert "Edit" in node.blocked_tools
    assert "Write(test_*)" in node.allowed_exceptions
    assert "Edit(test_*)" in node.allowed_exceptions

def test_tdd_red_auto_transitions():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    red = next(n for n in config.nodes if n.name == "red")
    assert red.auto_transition == "start_fixing"

def test_tdd_green_auto_transitions():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    green = next(n for n in config.nodes if n.name == "green")
    assert green.auto_transition == "start_linting"

def test_tdd_has_exit_gate_on_writing_tests():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    exit_gates = [g for g in config.gates if g.trigger == "on_exit"]
    assert any("writing_tests" in g.applies_to for g in exit_gates)

def test_tdd_has_enter_gate_on_linting():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    enter_gates = [g for g in config.gates if g.trigger == "on_enter"]
    linting_gate = next((g for g in enter_gates if "linting" in g.applies_to), None)
    assert linting_gate is not None
    assert linting_gate.routes == {"pass": "lint_pass", "fail": "lint_fail"}
