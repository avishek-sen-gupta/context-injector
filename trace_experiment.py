#!/usr/bin/env python3
"""Trace experiments: run multiple tests through the execution tracer."""

import tempfile
from tracer import trace_test
from parenthood import LineSetStrategy, build_abstraction_tree, render_hierarchy
from tests.test_v4_engine import make_simple_machine
from governor_v4.engine import GovernorV4


def test_transition_with_valid_evidence():
    with tempfile.TemporaryDirectory() as tmp_path:
        gov = GovernorV4(
            config=make_simple_machine(), state_dir=str(tmp_path), session_id="t"
        )
        key = gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/",
            output="FAILED test_auth.py",
            exit_code=1,
        )
        result = gov.want_to_transition("fixing_tests", key)
        assert result["action"] == "allow"


def test_ungated_transition():
    with tempfile.TemporaryDirectory() as tmp_path:
        gov = GovernorV4(
            config=make_simple_machine(), state_dir=str(tmp_path), session_id="t"
        )
        key = gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        gov.want_to_transition("fixing_tests", key)
        result = gov.want_to_transition("writing_tests")
        assert result["action"] == "allow"
        assert gov.current_phase == "writing_tests"


ALL_TESTS = [
    test_transition_with_valid_evidence,
    test_ungated_transition,
]


if __name__ == "__main__":
    # Phase 1: Trace all tests
    trees = {}
    for test_fn in ALL_TESTS:
        trees[test_fn.__name__] = trace_test(test_fn)

    # Phase 2: Parenthood analysis
    print()
    print("=" * 80)
    strategy = LineSetStrategy()
    adjacency = build_abstraction_tree(trees, strategy)
    print(render_hierarchy(adjacency, set(trees.keys())))
    print("=" * 80)
