# gates/reassignment.py
"""ReassignmentGate — beniget-based reassignment detection.

Uses def-use chain analysis to detect variables, parameters, or names
that are assigned more than once within the same scope. This catches
re-binding that structural pattern matching (ast-grep) cannot detect.
"""

import ast
import os
from collections import defaultdict

import beniget

from gates.base import Gate, GateContext, GateResult, GateVerdict


class ReassignmentGate(Gate):
    """Gate that detects variable/parameter reassignment in Python files."""

    name = "reassignment"

    def evaluate(self, ctx: GateContext) -> GateResult:
        py_files = [
            f for f in dict.fromkeys(ctx.recent_files)
            if f.endswith(".py") and os.path.exists(f)
        ]
        if not py_files:
            return GateResult(GateVerdict.PASS)

        all_violations = []
        for filepath in py_files:
            all_violations.extend(self._check_file(filepath))

        if not all_violations:
            return GateResult(GateVerdict.PASS)

        return GateResult(
            GateVerdict.FAIL,
            message=self._format_violations(all_violations),
            issues=[f"{v['name']}:{v['file']}:{v['line']}" for v in all_violations],
        )

    @staticmethod
    def _check_file(filepath: str) -> list[dict]:
        """Analyze a single file for reassignment violations."""
        try:
            with open(filepath) as f:
                source = f.read()
            tree = ast.parse(source, filename=filepath)
        except (SyntaxError, OSError):
            return []

        duc = beniget.DefUseChains()
        try:
            duc.visit(tree)
        except Exception:
            return []

        violations = []
        for scope_node, local_defs in duc.locals.items():
            # Group definitions by name within this scope
            names: dict[str, list] = defaultdict(list)
            for chain in local_defs:
                node = chain.node
                name = chain.name()
                # Skip scope-defining nodes (FunctionDef, ClassDef, etc.)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                # Skip import statements
                if isinstance(node, (ast.Import, ast.ImportFrom, ast.alias)):
                    continue
                names[name].append(node)

            # Any name with >1 definition in this scope is a reassignment
            for name, nodes in names.items():
                if len(nodes) > 1:
                    # Report the second (and later) definitions
                    for node in nodes[1:]:
                        lineno = getattr(node, "lineno", 0)
                        scope_desc = _scope_description(scope_node)
                        violations.append({
                            "name": name,
                            "file": filepath,
                            "line": lineno,
                            "scope": scope_desc,
                        })

        return violations

    @staticmethod
    def _format_violations(violations: list[dict]) -> str:
        lines = [f"GATE: reassignment — {len(violations)} violation(s) found:"]
        for v in violations:
            lines.append(
                f"  - '{v['name']}' reassigned at {v['file']}:{v['line']} "
                f"(scope: {v['scope']})"
            )
        lines.append("")
        lines.append("Use immutable patterns — avoid rebinding variables.")
        return "\n".join(lines)


def _scope_description(node: ast.AST) -> str:
    if isinstance(node, ast.Module):
        return "module"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"function {node.name}()"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    return type(node).__name__
