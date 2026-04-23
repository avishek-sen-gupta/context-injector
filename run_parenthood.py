#!/usr/bin/env python3
"""Run parenthood analysis across the full test suite."""

import pytest
from tracer import trace_context
from parenthood import LineSetStrategy, build_abstraction_tree, render_hierarchy


class ParenthoodPlugin:
    """Pytest plugin that traces each test and builds a parenthood hierarchy."""

    def __init__(self):
        self.trees = {}

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        with trace_context() as tree:
            outcome = yield
        self.trees[item.nodeid] = tree

    def pytest_sessionfinish(self, session):
        if not self.trees:
            return
        print()
        print("=" * 80)
        strategy = LineSetStrategy()
        adjacency = build_abstraction_tree(self.trees, strategy)
        print(render_hierarchy(adjacency, set(self.trees.keys())))
        print("=" * 80)


if __name__ == "__main__":
    plugin = ParenthoodPlugin()
    pytest.main(["tests/", "-q", "-p", "no:cacheprovider"], plugins=[plugin])
