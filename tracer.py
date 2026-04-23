#!/usr/bin/env python3
"""Trace every project-local Python line executed by a callable, print as a call tree."""

import sys
import os
import threading
from contextlib import contextmanager

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
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
        # But allow if it's under PROJECT_ROOT (which may be under prefix in venvs)
        if abs_path.startswith(PROJECT_ROOT):
            return True
        return False
    return abs_path.startswith(PROJECT_ROOT)


class CallTree:
    def __init__(self):
        self.roots = []
        self.stack = []  # stack of (node, depth)

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
