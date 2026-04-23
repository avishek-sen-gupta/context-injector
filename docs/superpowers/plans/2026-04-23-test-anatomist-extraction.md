# Test Anatomist Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the test hierarchy analysis code from `context-injector` into a standalone pip-installable repo called `test-anatomist`, with a pytest plugin that activates via `--anatomist`.

**Architecture:** Create a new repo with `src/` layout. Copy `tracer.py` and `parenthood.py` with import adjustments (bare → package-relative). Rewrite `run_parenthood.py` as a proper pytest plugin with CLI flags. Register via `pytest11` entry point.

**Tech Stack:** Python 3.10+, pytest, Hatchling build backend

---

## File Structure

| File | Role |
|---|---|
| `pyproject.toml` | Package metadata, build config, pytest11 entry point |
| `src/test_anatomist/__init__.py` | Re-exports public API |
| `src/test_anatomist/tracer.py` | CallTree, trace_context, trace_test, is_project_file |
| `src/test_anatomist/parenthood.py` | LineSetStrategy, HierarchyGraph, build_hierarchy |
| `src/test_anatomist/plugin.py` | Pytest plugin with --anatomist flag |
| `tests/test_tracer.py` | Tests for tracer module |
| `tests/test_parenthood.py` | Tests for parenthood module |
| `tests/test_plugin.py` | Tests for pytest plugin |

---

### Task 1: Create repo and pyproject.toml

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Create the repo directory and initialise git**

```bash
mkdir -p /Users/asgupta/code/test-anatomist
cd /Users/asgupta/code/test-anatomist
git init
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "test-anatomist"
version = "0.1.0"
description = "Trace test execution and reveal parent-child abstraction hierarchies"
requires-python = ">=3.10"
dependencies = ["pytest"]

[project.entry-points.pytest11]
test_anatomist = "test_anatomist.plugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/test_anatomist"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create directory structure**

```bash
mkdir -p src/test_anatomist tests
touch src/test_anatomist/__init__.py
touch src/test_anatomist/tracer.py
touch src/test_anatomist/parenthood.py
touch src/test_anatomist/plugin.py
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: scaffold test-anatomist package"
```

---

### Task 2: Copy and adapt tracer module

**Files:**
- Create: `tests/test_tracer.py`
- Modify: `src/test_anatomist/tracer.py`

The tracer module is self-contained (stdlib only). The only change needed is making `PROJECT_ROOT` dynamic — in the original repo it's hardcoded to the repo root, but as a library it needs to resolve relative to the *consuming* project's working directory, not the package install location.

- [ ] **Step 1: Write the tests**

These are adapted from `context-injector/tests/test_tracer.py`, with imports changed to `from test_anatomist.tracer import ...`.

```python
# tests/test_tracer.py
import sys

from test_anatomist.tracer import trace_context


def test_trace_context_captures_lines():
    """trace_context yields a CallTree that records executed lines."""

    def sample():
        x = 1
        y = 2
        return x + y

    with trace_context() as tree:
        sample()

    assert len(tree.roots) > 0
    assert any(root["func"] == "sample" for root in tree.roots)


def test_trace_context_stops_tracing_after_exit():
    """After exiting the context, tracing is off."""

    with trace_context() as tree:
        pass

    assert sys.gettrace() is None


def test_trace_context_stops_on_exception():
    """Tracing is stopped even if the body raises."""

    try:
        with trace_context() as tree:
            raise ValueError("boom")
    except ValueError:
        pass

    assert sys.gettrace() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/test-anatomist && pip install -e . && python3 -m pytest tests/test_tracer.py -v`
Expected: FAIL — `trace_context` not yet implemented (empty module).

- [ ] **Step 3: Write the tracer module**

Copy from `context-injector/tracer.py`. The one adaptation: change `PROJECT_ROOT` to use `os.getcwd()` instead of `os.path.dirname(os.path.abspath(__file__))`, so it filters based on the consuming project's working directory rather than the installed package location.

```python
# src/test_anatomist/tracer.py
"""Trace every project-local Python line executed by a callable, print as a call tree."""

import sys
import os
import threading
from contextlib import contextmanager

# --- Configuration ---
# Use cwd so the filter works relative to the consuming project, not this package's install location.
PROJECT_ROOT = os.getcwd()
STDLIB_PREFIXES = (
    sys.prefix,
    sys.exec_prefix,
    os.path.dirname(os.__file__),  # stdlib dir
)
SITE_PACKAGES = "site-packages"


def is_project_file(filename):
    """Return True if filename belongs to this project (not stdlib, not site-packages)."""
    if not filename:
        return False
    abs_path = os.path.abspath(filename)
    if SITE_PACKAGES in abs_path:
        return False
    if any(abs_path.startswith(p) for p in STDLIB_PREFIXES):
        if abs_path.startswith(PROJECT_ROOT):
            return True
        return False
    return abs_path.startswith(PROJECT_ROOT)


class CallTree:
    def __init__(self):
        self.roots = []
        self.stack = []

    def push_call(self, filename, funcname, lineno):
        rel = os.path.relpath(filename, PROJECT_ROOT)
        node = {
            "type": "call",
            "func": funcname,
            "file": rel,
            "line": lineno,
            "children": [],
            "lines": [],
        }
        if self.stack:
            self.stack[-1]["children"].append(node)
        else:
            self.roots.append(node)
        self.stack.append(node)

    def pop_call(self):
        if self.stack:
            self.stack.pop()

    def add_line(self, filename, lineno):
        rel = os.path.relpath(filename, PROJECT_ROOT)
        if self.stack:
            self.stack[-1]["lines"].append((rel, lineno))

    def render(self, max_depth=None):
        lines = []
        for root in self.roots:
            self._render_node(root, "", True, lines, 0, max_depth)
        return "\n".join(lines)

    def _render_node(self, node, prefix, is_last, lines, depth, max_depth):
        if max_depth is not None and depth > max_depth:
            return
        connector = "└── " if is_last else "├── "
        line_count = len(node["lines"])
        child_count = len(node["children"])
        label = f'{node["func"]}  ({node["file"]}:{node["line"]})  [{line_count} lines, {child_count} calls]'
        lines.append(f"{prefix}{connector}{label}")

        new_prefix = prefix + ("    " if is_last else "│   ")
        children = node["children"]
        for i, child in enumerate(children):
            self._render_node(
                child, new_prefix, i == len(children) - 1, lines, depth + 1, max_depth
            )


@contextmanager
def trace_context():
    """Yield a CallTree that records project-local execution while the context is active."""
    tree = CallTree()

    def tracer(frame, event, arg):
        if threading.current_thread() is not threading.main_thread():
            return None
        filename = frame.f_code.co_filename
        if not is_project_file(filename):
            return None

        if event == "call":
            tree.push_call(filename, frame.f_code.co_name, frame.f_lineno)
            return tracer
        elif event == "line":
            tree.add_line(filename, frame.f_lineno)
        elif event == "return":
            tree.pop_call()
        return tracer

    sys.settrace(tracer)
    try:
        yield tree
    finally:
        sys.settrace(None)


def trace_test(test_fn, label=None):
    """Trace a zero-arg callable and print its execution tree.

    Returns the CallTree for programmatic use.
    """
    label = label or getattr(test_fn, "__name__", "unknown")
    with trace_context() as tree:
        test_fn()

    print("=" * 80)
    print(f"EXECUTION TREE: {label}")
    print("=" * 80)
    print()
    print(tree.render())
    print()
    print(f"Total top-level calls: {len(tree.roots)}")
    return tree
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tracer.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/test_anatomist/tracer.py tests/test_tracer.py
git commit -m "feat: add tracer module with CallTree and trace_context"
```

---

### Task 3: Copy and adapt parenthood module

**Files:**
- Create: `tests/test_parenthood.py`
- Modify: `src/test_anatomist/parenthood.py`

The only change is the import: `from tracer import CallTree` becomes `from .tracer import CallTree`.

- [ ] **Step 1: Write the tests**

Adapted from `context-injector/tests/test_parenthood.py` with imports changed to `from test_anatomist.tracer import CallTree` and `from test_anatomist.parenthood import ...`.

```python
# tests/test_parenthood.py
"""Test parenthood detection via execution trace comparison."""

from test_anatomist.tracer import CallTree
from test_anatomist.parenthood import LineSetStrategy, build_hierarchy


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
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        assert graph.adjacency == {}

    def test_transitive_reduction(self):
        """A->B->C should not produce direct A->C edge."""
        a = _make_tree({"x": [("f.py", i) for i in range(1, 11)]})
        b = _make_tree({"y": [("f.py", i) for i in range(1, 8)]})
        c = _make_tree({"z": [("f.py", i) for i in range(1, 4)]})
        trees = {"test_a": a, "test_b": b, "test_c": c}
        graph = build_hierarchy(trees, LineSetStrategy(), threshold=0.95)
        assert "test_b" in [name for name, _ in graph.adjacency.get("test_a", [])]
        assert "test_c" in [name for name, _ in graph.adjacency.get("test_b", [])]
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
        c = _make_tree({"z": [("g.py", 99)]})
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_parenthood.py -v`
Expected: FAIL — `ImportError: cannot import name 'LineSetStrategy' from 'test_anatomist.parenthood'`

- [ ] **Step 3: Write the parenthood module**

Copy from `context-injector/parenthood.py` with one import change: `from tracer import CallTree` → `from .tracer import CallTree`.

```python
# src/test_anatomist/parenthood.py
"""Test parenthood detection via execution trace comparison."""

from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property
from typing import Protocol
from .tracer import CallTree


class ParenthoodStrategy(Protocol):
    def containment_score(self, parent: CallTree, child: CallTree) -> float:
        """Return 0.0-1.0: fraction of child's footprint covered by parent."""
        ...


def _flatten_lines(tree: CallTree) -> set[tuple[str, int]]:
    """Recursively collect all (file, lineno) pairs from a CallTree."""
    result = set()

    def walk(node):
        for line in node["lines"]:
            result.add(line)
        for child in node["children"]:
            walk(child)

    for root in tree.roots:
        walk(root)
    return result


class LineSetStrategy:
    def containment_score(self, parent: CallTree, child: CallTree) -> float:
        child_set = _flatten_lines(child)
        if not child_set:
            return 0.0
        parent_set = _flatten_lines(parent)
        return len(child_set & parent_set) / len(child_set)


@dataclass
class HierarchyGraph:
    """DAG of test parent-child relationships with multiple renderers."""

    adjacency: dict[str, list[tuple[str, float]]]
    all_names: set[str]
    threshold: float

    @cached_property
    def roots(self) -> list[str]:
        all_children = {
            name for children in self.adjacency.values() for name, _ in children
        }
        return sorted(n for n in self.all_names if n not in all_children)

    def render_text(self) -> str:
        if not self.adjacency:
            return "No parent-child relationships found at this threshold."

        lines = [f"TEST ABSTRACTION HIERARCHY (threshold={self.threshold}):"]
        seen: set[str] = set()

        def _render(name, score, prefix, is_last):
            connector = "└── " if is_last else "├── "
            score_str = f" ({score:.2f})" if score is not None else ""
            if name in seen:
                lines.append(
                    f"{prefix}{connector}{name}{score_str} (see above)"
                )
                return
            seen.add(name)
            lines.append(f"{prefix}{connector}{name}{score_str}")
            children = self.adjacency.get(name, [])
            if not children:
                return
            children = sorted(children, key=lambda x: x[1], reverse=True)
            new_prefix = prefix + ("    " if is_last else "│   ")
            for i, (child, child_score) in enumerate(children):
                _render(child, child_score, new_prefix, i == len(children) - 1)

        for i, root in enumerate(self.roots):
            _render(root, None, "", i == len(self.roots) - 1)

        return "\n".join(lines)

    def render_mermaid(self) -> str:
        seen_ids: dict[str, str] = {}
        counter = [0]

        def get_id(name):
            if name not in seen_ids:
                seen_ids[name] = f"n{counter[0]}"
                counter[0] += 1
            return seen_ids[name]

        lines = ["graph TD"]
        all_nodes = set(self.adjacency.keys())
        for children in self.adjacency.values():
            for c, _ in children:
                all_nodes.add(c)

        for name in sorted(all_nodes):
            nid = get_id(name)
            lines.append(f'    {nid}["{name}"]')

        for parent in sorted(self.adjacency.keys()):
            pid = get_id(parent)
            for child, score in sorted(
                self.adjacency[parent], key=lambda x: x[1], reverse=True
            ):
                cid = get_id(child)
                lines.append(f"    {pid} -->|{score:.0%}| {cid}")

        return "\n".join(lines)


def build_hierarchy(
    trees: dict[str, CallTree],
    strategy: ParenthoodStrategy,
    threshold: float = 0.95,
) -> HierarchyGraph:
    """Build a parent-child DAG from test call trees.

    Returns a HierarchyGraph with adjacency, roots, and render methods.
    Only direct (transitively reduced) edges are included.
    """
    footprints = {name: _flatten_lines(tree) for name, tree in trees.items()}
    names = list(trees.keys())

    edges: dict[str, list[tuple[str, float]]] = {}
    for a in names:
        for b in names:
            if a == b:
                continue
            if len(footprints[a]) <= len(footprints[b]):
                continue
            score = strategy.containment_score(trees[a], trees[b])
            if score >= threshold:
                edges.setdefault(a, []).append((b, score))

    reduced: dict[str, list[tuple[str, float]]] = {}
    for parent, children in edges.items():
        child_names = {name for name, _ in children}
        redundant = set()
        for child_name, _ in children:
            if child_name in edges:
                for grandchild_name, _ in edges[child_name]:
                    if grandchild_name in child_names:
                        redundant.add(grandchild_name)
        kept = [(name, score) for name, score in children if name not in redundant]
        if kept:
            reduced[parent] = kept

    return HierarchyGraph(
        adjacency=reduced, all_names=set(trees.keys()), threshold=threshold
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tracer.py tests/test_parenthood.py -v`
Expected: All 21 tests PASS (3 tracer + 18 parenthood).

- [ ] **Step 5: Commit**

```bash
git add src/test_anatomist/parenthood.py tests/test_parenthood.py
git commit -m "feat: add parenthood module with HierarchyGraph and build_hierarchy"
```

---

### Task 4: Create __init__.py with public API re-exports

**Files:**
- Modify: `src/test_anatomist/__init__.py`

- [ ] **Step 1: Write __init__.py**

```python
# src/test_anatomist/__init__.py
"""Test Anatomist — trace test execution and reveal parent-child abstraction hierarchies."""

from .tracer import CallTree, trace_context, trace_test
from .parenthood import LineSetStrategy, HierarchyGraph, build_hierarchy

__all__ = [
    "CallTree",
    "trace_context",
    "trace_test",
    "LineSetStrategy",
    "HierarchyGraph",
    "build_hierarchy",
]
```

- [ ] **Step 2: Verify imports work**

Run: `python3 -c "from test_anatomist import CallTree, trace_context, build_hierarchy; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/test_anatomist/__init__.py
git commit -m "feat: re-export public API from __init__.py"
```

---

### Task 5: Create pytest plugin with --anatomist flag

**Files:**
- Create: `tests/test_plugin.py`
- Modify: `src/test_anatomist/plugin.py`

- [ ] **Step 1: Write the plugin tests**

```python
# tests/test_plugin.py
"""Tests for the pytest plugin."""

import pytest


def test_plugin_noop_without_flag(pytester):
    """Without --anatomist, plugin produces no hierarchy output."""
    pytester.makepyfile(
        """
        def test_one():
            assert 1 + 1 == 2
        """
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)
    assert "ABSTRACTION HIERARCHY" not in result.stdout.str()


def test_plugin_outputs_hierarchy_with_flag(pytester):
    """With --anatomist, plugin prints hierarchy after session."""
    pytester.makepyfile(
        """
        def test_one():
            x = 1
            y = 2
            assert x + y == 3

        def test_two():
            x = 1
            assert x == 1
        """
    )
    result = pytester.runpytest("--anatomist", "-s")
    result.assert_outcomes(passed=2)
    # Should have some output section (may or may not find relationships)
    stdout = result.stdout.str()
    assert "ANATOMIST" in stdout or "No parent-child" in stdout


def test_plugin_respects_threshold_flag(pytester):
    """--anatomist-threshold is accepted without error."""
    pytester.makepyfile(
        """
        def test_one():
            assert True
        """
    )
    result = pytester.runpytest("--anatomist", "--anatomist-threshold=0.85", "-s")
    result.assert_outcomes(passed=1)


def test_plugin_respects_format_flag(pytester):
    """--anatomist-format=mermaid produces Mermaid output."""
    pytester.makepyfile(
        """
        def test_one():
            x = 1
            y = 2
            assert x + y == 3

        def test_two():
            x = 1
            assert x == 1
        """
    )
    result = pytester.runpytest(
        "--anatomist", "--anatomist-format=mermaid", "-s"
    )
    result.assert_outcomes(passed=2)
    stdout = result.stdout.str()
    assert "graph TD" in stdout or "No parent-child" in stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_plugin.py -v`
Expected: FAIL — plugin module is empty, `--anatomist` flag not recognized.

- [ ] **Step 3: Write the plugin**

```python
# src/test_anatomist/plugin.py
"""Pytest plugin that traces tests and builds an abstraction hierarchy.

Activated by passing --anatomist to pytest. No-op otherwise.
"""

import pytest
from .tracer import trace_context
from .parenthood import LineSetStrategy, build_hierarchy


def pytest_addoption(parser):
    group = parser.getgroup("anatomist", "Test Anatomist")
    group.addoption(
        "--anatomist",
        action="store_true",
        default=False,
        help="Enable test tracing and hierarchy analysis",
    )
    group.addoption(
        "--anatomist-threshold",
        type=float,
        default=0.95,
        help="Containment threshold for parent-child relationships (default: 0.95)",
    )
    group.addoption(
        "--anatomist-format",
        choices=["text", "mermaid"],
        default="text",
        help="Output format for the hierarchy (default: text)",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if not item.config.getoption("anatomist"):
        yield
        return
    with trace_context() as tree:
        outcome = yield
    item._anatomist_tree = tree


def pytest_sessionfinish(session):
    if not session.config.getoption("anatomist"):
        return

    trees = {}
    for item in session.items:
        tree = getattr(item, "_anatomist_tree", None)
        if tree is not None:
            trees[item.nodeid] = tree

    if not trees:
        return

    threshold = session.config.getoption("anatomist_threshold")
    fmt = session.config.getoption("anatomist_format")

    strategy = LineSetStrategy()
    graph = build_hierarchy(trees, strategy, threshold=threshold)

    tw = session.config.get_terminal_writer()
    tw.line()
    tw.sep("=", "ANATOMIST")
    if fmt == "mermaid":
        tw.line(graph.render_mermaid())
    else:
        tw.line(graph.render_text())
    tw.sep("=", "ANATOMIST")
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS (3 tracer + 18 parenthood + 4 plugin = 25 total).

- [ ] **Step 5: Commit**

```bash
git add src/test_anatomist/plugin.py tests/test_plugin.py
git commit -m "feat: add pytest plugin with --anatomist flag"
```

---

### Task 6: End-to-end verification and initial push

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All 25 tests PASS.

- [ ] **Step 2: Verify plugin works on itself**

Run: `python3 -m pytest tests/ --anatomist --anatomist-threshold=0.85 -s`
Expected: Tests pass, followed by an ANATOMIST section showing the hierarchy of test-anatomist's own tests.

- [ ] **Step 3: Create GitHub repo and push**

```bash
gh repo create avishek-sen-gupta/test-anatomist --public --source=. --push
```

- [ ] **Step 4: Verify editable install works from another repo**

```bash
cd /Users/asgupta/code/context-injector
pip install -e ../test-anatomist
python3 -m pytest tests/ --anatomist -s -q
```

Expected: context-injector's 178 tests run, followed by the ANATOMIST hierarchy output.
