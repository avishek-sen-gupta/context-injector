"""Test parenthood detection via execution trace comparison."""

from tracer import CallTree
from parenthood import LineSetStrategy


def _make_tree(lines_by_func):
    """Build a CallTree from a dict of {funcname: [(file, lineno), ...]}."""
    tree = CallTree()
    for func, lines in lines_by_func.items():
        tree.push_call(f"/proj/{func}.py", func, 1)
        for file, lineno in lines:
            tree.add_line(file, lineno)
        tree.pop_call()
    return tree


class TestLineSetStrategy:
    def test_perfect_containment(self):
        parent = _make_tree({"a": [("f.py", 1), ("f.py", 2), ("f.py", 3)]})
        child = _make_tree({"b": [("f.py", 1), ("f.py", 2)]})
        strategy = LineSetStrategy()
        assert strategy.containment_score(parent, child) == 1.0

    def test_partial_containment(self):
        parent = _make_tree({"a": [("f.py", 1), ("f.py", 2)]})
        child = _make_tree({"b": [("f.py", 1), ("f.py", 3)]})
        strategy = LineSetStrategy()
        assert strategy.containment_score(parent, child) == 0.5

    def test_no_overlap(self):
        parent = _make_tree({"a": [("f.py", 1)]})
        child = _make_tree({"b": [("g.py", 1)]})
        strategy = LineSetStrategy()
        assert strategy.containment_score(parent, child) == 0.0

    def test_empty_child_returns_zero(self):
        parent = _make_tree({"a": [("f.py", 1)]})
        child = CallTree()
        strategy = LineSetStrategy()
        assert strategy.containment_score(parent, child) == 0.0

    def test_nested_calls_flattened(self):
        """Lines in nested children are included in the footprint."""
        tree = CallTree()
        tree.push_call("/proj/a.py", "outer", 1)
        tree.add_line("a.py", 10)
        tree.push_call("/proj/b.py", "inner", 5)
        tree.add_line("b.py", 20)
        tree.pop_call()
        tree.pop_call()

        child = _make_tree({"c": [("a.py", 10), ("b.py", 20)]})
        strategy = LineSetStrategy()
        assert strategy.containment_score(tree, child) == 1.0
