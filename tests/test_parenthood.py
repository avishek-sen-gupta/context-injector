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


from parenthood import build_hierarchy


class TestBuildHierarchy:
    def test_simple_parent_child(self):
        """A with superset lines is parent of B."""
        parent = _make_tree({"a": [("f.py", 1), ("f.py", 2), ("f.py", 3)]})
        child = _make_tree({"b": [("f.py", 1), ("f.py", 2)]})
        trees = {"parent_test": parent, "child_test": child}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        assert "parent_test" in graph.adjacency
        assert len(graph.adjacency["parent_test"]) == 1
        assert graph.adjacency["parent_test"][0][0] == "child_test"

    def test_no_relationship_when_equal_size(self):
        """Same footprint size = no parent relationship."""
        a = _make_tree({"a": [("f.py", 1), ("f.py", 2)]})
        b = _make_tree({"b": [("f.py", 1), ("f.py", 2)]})
        trees = {"test_a": a, "test_b": b}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        assert graph.adjacency == {}

    def test_below_threshold_excluded(self):
        """Containment below threshold is not a parent relationship."""
        parent = _make_tree({"a": [("f.py", 1), ("f.py", 2), ("f.py", 3)]})
        child = _make_tree({"b": [("f.py", 1), ("g.py", 99)]})
        trees = {"parent_test": parent, "child_test": child}
        # Only 50% containment, threshold is 95%
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        assert graph.adjacency == {}

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
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        # A is parent of B, B is parent of C
        assert "test_b" in [name for name, _ in graph.adjacency.get("test_a", [])]
        assert "test_c" in [name for name, _ in graph.adjacency.get("test_b", [])]
        # A should NOT be direct parent of C (transitive reduction)
        assert "test_c" not in [name for name, _ in graph.adjacency.get("test_a", [])]

    def test_roots_have_no_parents(self):
        """Tests that are not children of anything don't appear as values."""
        a = _make_tree({"x": [("f.py", i) for i in range(1, 6)]})
        b = _make_tree({"y": [("f.py", i) for i in range(1, 4)]})
        trees = {"test_a": a, "test_b": b}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        assert "test_a" in graph.roots
        assert "test_b" not in graph.roots or "test_b" in [
            name for name, _ in graph.adjacency.get("test_a", [])
        ]

    def test_roots_include_isolated(self):
        """Isolated tests (no parents, no children) are roots."""
        a = _make_tree({"x": [("f.py", 1), ("f.py", 2), ("f.py", 3)]})
        b = _make_tree({"y": [("f.py", 1), ("f.py", 2)]})
        c = _make_tree({"z": [("g.py", 99)]})  # no overlap with a or b
        trees = {"test_a": a, "test_b": b, "test_c": c}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        assert "test_c" in graph.roots


class TestRenderText:
    def test_simple_hierarchy(self):
        parent = _make_tree({"a": [("f.py", 1), ("f.py", 2), ("f.py", 3)]})
        child_b = _make_tree({"b": [("f.py", 1), ("f.py", 2)]})
        child_c = _make_tree({"c": [("f.py", 1)]})
        trees = {"test_a": parent, "test_b": child_b, "test_c": child_c}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        output = graph.render_text()
        assert "test_a" in output
        assert "test_b" in output

    def test_nested_tree(self):
        """A->B->C renders as a nested tree."""
        a = _make_tree({"x": [("f.py", i) for i in range(1, 11)]})
        b = _make_tree({"y": [("f.py", i) for i in range(1, 8)]})
        c = _make_tree({"z": [("f.py", i) for i in range(1, 4)]})
        trees = {"test_a": a, "test_b": b, "test_c": c}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        output = graph.render_text()
        lines = output.split("\n")
        depth_b = next(len(l) - len(l.lstrip()) for l in lines if "test_b" in l)
        depth_c = next(len(l) - len(l.lstrip()) for l in lines if "test_c" in l)
        assert depth_c > depth_b

    def test_shared_child_deduplicated(self):
        """A shared child is expanded once, then shown as 'see above'."""
        a = _make_tree({"x": [("f.py", i) for i in range(1, 6)]})
        b = _make_tree({"y": [("f.py", i) for i in range(1, 4)]})
        shared = _make_tree({"z": [("f.py", 1)]})
        trees = {"test_a": a, "test_b": b, "test_shared": shared}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        output = graph.render_text()
        shared_lines = [l for l in output.split("\n") if "test_shared" in l]
        see_above = [l for l in shared_lines if "see above" in l]
        assert len(see_above) == len(shared_lines) - 1

    def test_empty_adjacency(self):
        a = _make_tree({"x": [("f.py", 1)]})
        b = _make_tree({"y": [("g.py", 1)]})
        trees = {"test_a": a, "test_b": b}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        output = graph.render_text()
        assert "No parent-child relationships found" in output


class TestRenderMermaid:
    def test_produces_graph_td(self):
        a = _make_tree({"x": [("f.py", i) for i in range(1, 6)]})
        b = _make_tree({"y": [("f.py", i) for i in range(1, 4)]})
        trees = {"test_a": a, "test_b": b}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        output = graph.render_mermaid()
        assert "graph TD" in output

    def test_contains_edge(self):
        a = _make_tree({"x": [("f.py", i) for i in range(1, 6)]})
        b = _make_tree({"y": [("f.py", i) for i in range(1, 4)]})
        trees = {"test_a": a, "test_b": b}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        output = graph.render_mermaid()
        assert "-->" in output
        assert "test_a" in output
        assert "test_b" in output

    def test_empty_graph(self):
        a = _make_tree({"x": [("f.py", 1)]})
        b = _make_tree({"y": [("g.py", 1)]})
        trees = {"test_a": a, "test_b": b}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        output = graph.render_mermaid()
        assert "graph TD" in output
        assert "-->" not in output
