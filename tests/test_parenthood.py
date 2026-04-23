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


from parenthood import build_abstraction_tree


class TestBuildAbstractionTree:
    def test_simple_parent_child(self):
        """A with superset lines is parent of B."""
        parent = _make_tree({"a": [("f.py", 1), ("f.py", 2), ("f.py", 3)]})
        child = _make_tree({"b": [("f.py", 1), ("f.py", 2)]})
        trees = {"parent_test": parent, "child_test": child}
        result = build_abstraction_tree(trees, LineSetStrategy(), threshold=0.95)
        assert "parent_test" in result
        assert len(result["parent_test"]) == 1
        assert result["parent_test"][0][0] == "child_test"

    def test_no_relationship_when_equal_size(self):
        """Same footprint size = no parent relationship."""
        a = _make_tree({"a": [("f.py", 1), ("f.py", 2)]})
        b = _make_tree({"b": [("f.py", 1), ("f.py", 2)]})
        trees = {"test_a": a, "test_b": b}
        result = build_abstraction_tree(trees, LineSetStrategy(), threshold=0.95)
        assert result == {}

    def test_below_threshold_excluded(self):
        """Containment below threshold is not a parent relationship."""
        parent = _make_tree({"a": [("f.py", 1), ("f.py", 2), ("f.py", 3)]})
        child = _make_tree({"b": [("f.py", 1), ("g.py", 99)]})
        trees = {"parent_test": parent, "child_test": child}
        # Only 50% containment, threshold is 95%
        result = build_abstraction_tree(trees, LineSetStrategy(), threshold=0.95)
        assert result == {}

    def test_transitive_reduction(self):
        """A->B->C should not produce direct A->C edge."""
        a = _make_tree({"x": [("f.py", i) for i in range(1, 11)]})  # 10 lines
        b = _make_tree(
            {"y": [("f.py", i) for i in range(1, 8)]}
        )  # 7 lines, subset of A
        c = _make_tree(
            {"z": [("f.py", i) for i in range(1, 4)]}
        )  # 3 lines, subset of B
        trees = {"test_a": a, "test_b": b, "test_c": c}
        result = build_abstraction_tree(trees, LineSetStrategy(), threshold=0.95)
        # A is parent of B, B is parent of C
        assert "test_b" in [name for name, _ in result.get("test_a", [])]
        assert "test_c" in [name for name, _ in result.get("test_b", [])]
        # A should NOT be direct parent of C (transitive reduction)
        assert "test_c" not in [name for name, _ in result.get("test_a", [])]

    def test_roots_have_no_parents(self):
        """Tests that are not children of anything don't appear as values."""
        a = _make_tree({"x": [("f.py", i) for i in range(1, 6)]})
        b = _make_tree({"y": [("f.py", i) for i in range(1, 4)]})
        trees = {"test_a": a, "test_b": b}
        result = build_abstraction_tree(trees, LineSetStrategy(), threshold=0.95)
        all_children = {name for children in result.values() for name, _ in children}
        assert "test_a" not in all_children
