"""Test parenthood detection via execution trace comparison."""

from __future__ import annotations
from typing import Protocol
from tracer import CallTree


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



def build_abstraction_tree(
    trees: dict[str, CallTree],
    strategy: ParenthoodStrategy,
    threshold: float = 0.95,
) -> dict[str, list[tuple[str, float]]]:
    """Build a parent-child DAG from test call trees.

    Returns adjacency dict: {parent_name: [(child_name, score), ...]}.
    Only direct (transitively reduced) edges are included.
    """
    footprints = {name: _flatten_lines(tree) for name, tree in trees.items()}
    names = list(trees.keys())

    # Find all parent->child edges
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

    # Transitive reduction: remove A->C if A->B->C exists
    reduced: dict[str, list[tuple[str, float]]] = {}
    for parent, children in edges.items():
        child_names = {name for name, _ in children}
        # A child is redundant if it's reachable through another child
        redundant = set()
        for child_name, _ in children:
            if child_name in edges:
                for grandchild_name, _ in edges[child_name]:
                    if grandchild_name in child_names:
                        redundant.add(grandchild_name)
        kept = [(name, score) for name, score in children if name not in redundant]
        if kept:
            reduced[parent] = kept

    return reduced


def render_hierarchy(
    adjacency: dict[str, list[tuple[str, float]]],
    all_names: set[str],
    threshold: float = 0.95,
) -> str:
    """Render the abstraction hierarchy as a nested tree string."""
    if not adjacency:
        return "No parent-child relationships found at this threshold."

    all_children = {name for children in adjacency.values() for name, _ in children}
    roots = sorted(
        [n for n in all_names if n not in all_children]
    )

    lines = [f"TEST ABSTRACTION HIERARCHY (threshold={threshold}):"]

    def _render(name, score, prefix, is_last):
        connector = "└── " if is_last else "├── "
        score_str = f" ({score:.2f})" if score is not None else ""
        lines.append(f"{prefix}{connector}{name}{score_str}")
        children = adjacency.get(name, [])
        if not children:
            return
        children = sorted(children, key=lambda x: x[1], reverse=True)
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, (child, child_score) in enumerate(children):
            _render(child, child_score, new_prefix, i == len(children) - 1)

    for i, root in enumerate(roots):
        _render(root, None, "", i == len(roots) - 1)

    return "\n".join(lines)
