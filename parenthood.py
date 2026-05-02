"""Test parenthood detection via execution trace comparison."""

from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property
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
                lines.append(f"{prefix}{connector}{name}{score_str} (see above)")
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
