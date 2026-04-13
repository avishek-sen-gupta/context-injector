# gates/test_quality.py
"""TestQualityGate — AST-based test quality analysis.

Detects structurally invalid and weak tests at transition boundaries.
"""

import ast
import os
from dataclasses import dataclass

from gates.base import Gate, GateContext, GateResult, GateVerdict


@dataclass
class Issue:
    """A detected test quality issue."""
    category: str     # e.g. "no_assertions", "trivial_assertion"
    severity: str     # "hard" or "soft"
    file: str
    function: str
    line: int
    detail: str

    def __str__(self):
        return f"{self.category}:{self.file}:{self.line}"


class TestQualityGate(Gate):
    """Gate that evaluates test quality via AST analysis."""

    name = "test_quality"

    def evaluate(self, ctx: GateContext) -> GateResult:
        test_files = [f for f in ctx.recent_files if self._is_test_file(f)]
        if not test_files:
            return GateResult(GateVerdict.PASS)

        issues: list[Issue] = []
        for path in test_files:
            if not os.path.exists(path):
                continue
            source = open(path).read()
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError:
                continue
            for func in self._extract_test_functions(tree):
                issues.extend(self._analyze_function(func, path))

        hard = [i for i in issues if i.severity == "hard"]
        soft = [i for i in issues if i.severity == "soft"]

        if hard:
            return GateResult(
                GateVerdict.FAIL,
                message=self._format_issues(hard),
                issues=[str(i) for i in hard],
            )
        if soft:
            return GateResult(
                GateVerdict.REVIEW,
                message=self._format_review_prompt(soft),
                issues=[str(i) for i in soft],
            )
        return GateResult(GateVerdict.PASS)

    @staticmethod
    def _is_test_file(path: str) -> bool:
        return os.path.basename(path).startswith("test_") and path.endswith(".py")

    def _extract_test_functions(self, tree: ast.Module) -> list[ast.FunctionDef]:
        funcs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    funcs.append(node)
        return funcs

    def _analyze_function(self, func: ast.FunctionDef, path: str) -> list[Issue]:
        issues = []
        basename = os.path.basename(path)

        # Check for xfail decorator
        for decorator in func.decorator_list:
            if self._is_xfail(decorator):
                issues.append(Issue(
                    "xfail_abuse", "hard", basename, func.name, func.lineno,
                    "@pytest.mark.xfail decorator",
                ))

        # Check for skip/xfail calls in body
        for node in ast.walk(func):
            if self._is_skip_call(node):
                issues.append(Issue(
                    "skip_abuse", "hard", basename, func.name, node.lineno,
                    "pytest.skip() call",
                ))
            if self._is_xfail_call(node):
                issues.append(Issue(
                    "xfail_abuse", "hard", basename, func.name, node.lineno,
                    "pytest.xfail() call",
                ))

        # Extract assertions
        asserts = self._find_assertions(func)
        has_pytest_raises = self._has_pytest_raises(func)

        if not asserts and not has_pytest_raises:
            issues.append(Issue(
                "no_assertions", "hard", basename, func.name, func.lineno,
                "No assert statements found",
            ))
            return issues  # No point checking further

        # Check for trivial assertions
        for assert_node in asserts:
            if self._is_trivial_assertion(assert_node):
                issues.append(Issue(
                    "trivial_assertion", "hard", basename, func.name, assert_node.lineno,
                    "Trivial assertion (assert True/literal)",
                ))

        # Soft violations: only flag if no hard issues found and there are assertions
        if not issues and asserts:
            soft = self._check_soft_violations(asserts, func, path)
            issues.extend(soft)

        return issues

    def _find_assertions(self, func: ast.FunctionDef) -> list[ast.Assert]:
        return [n for n in ast.walk(func) if isinstance(n, ast.Assert)]

    def _has_pytest_raises(self, func: ast.FunctionDef) -> bool:
        """Check if function uses pytest.raises context manager."""
        for node in ast.walk(func):
            if isinstance(node, ast.With):
                for item in node.items:
                    if self._is_pytest_raises_call(item.context_expr):
                        return True
        return False

    @staticmethod
    def _is_pytest_raises_call(node: ast.expr) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "raises":
            if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                return True
        return False

    @staticmethod
    def _is_trivial_assertion(node: ast.Assert) -> bool:
        test = node.test
        if isinstance(test, ast.Constant):
            return bool(test.value)  # assert True, assert 1, assert "literal"
        return False

    @staticmethod
    def _is_xfail(decorator) -> bool:
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "xfail"
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            return decorator.func.attr == "xfail"
        return False

    @staticmethod
    def _is_skip_call(node) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "skip":
            if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                return True
        return False

    @staticmethod
    def _is_xfail_call(node) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "xfail":
            if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                return True
        return False

    @staticmethod
    def _format_issues(issues: list[Issue]) -> str:
        lines = ["GATE: test_quality — blocked:"]
        for i in issues:
            lines.append(f"  - {i.file}::{i.function}:{i.line} — {i.detail}")
        return "\n".join(lines)

    @staticmethod
    def _format_review_prompt(issues: list[Issue]) -> str:
        lines = ["GATE: test_quality flagged potential issues:"]
        for i in issues:
            lines.append(f"  - {i.file}::{i.function}:{i.line} — {i.detail}")
        lines.append("")
        lines.append(
            "Review these tests — do they actually constrain the behavior you're "
            "implementing? If intentional, run pytest again to retry. "
            "Otherwise, strengthen the assertions first."
        )
        return "\n".join(lines)

    def _check_soft_violations(self, asserts: list[ast.Assert], func: ast.FunctionDef, path: str) -> list[Issue]:
        basename = os.path.basename(path)
        issues = []

        has_value_comparison = False
        all_none_checks = True
        all_membership_checks = True
        all_type_checks = True

        for a in asserts:
            kind = self._classify_assertion(a)
            if kind == "value_comparison":
                has_value_comparison = True
                all_none_checks = False
                all_membership_checks = False
                all_type_checks = False
            elif kind == "none_check":
                all_membership_checks = False
                all_type_checks = False
            elif kind == "membership_check":
                all_none_checks = False
                all_type_checks = False
            elif kind == "type_check":
                all_none_checks = False
                all_membership_checks = False
            else:
                all_none_checks = False
                all_membership_checks = False
                all_type_checks = False

        if not has_value_comparison and len(asserts) > 0:
            if all_none_checks:
                issues.append(Issue(
                    "none_only", "soft", basename, func.name, asserts[0].lineno,
                    "All assertions only check None/not None",
                ))
            elif all_membership_checks:
                issues.append(Issue(
                    "membership_only", "soft", basename, func.name, asserts[0].lineno,
                    "All assertions only check membership (in/not in) without verifying values",
                ))
            elif all_type_checks:
                issues.append(Issue(
                    "type_only", "soft", basename, func.name, asserts[0].lineno,
                    "All assertions only check types (isinstance) without verifying values",
                ))

        # Import overlap: same callable on both sides of ==
        overlap = self._check_import_overlap(asserts, func)
        if overlap:
            issues.append(Issue(
                "import_overlap", "soft", basename, func.name, overlap.lineno,
                "Same production function called on both sides of assertion",
            ))

        return issues

    def _classify_assertion(self, node: ast.Assert) -> str:
        """Classify an assertion into a category."""
        test = node.test

        # assert x is None / assert x is not None
        if isinstance(test, ast.Compare):
            if len(test.ops) == 1:
                op = test.ops[0]
                comparator = test.comparators[0]
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comparator, ast.Constant) and comparator.value is None:
                    return "none_check"
                if isinstance(op, (ast.In, ast.NotIn)):
                    return "membership_check"
                if isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.LtE, ast.GtE)):
                    return "value_comparison"

        # assert isinstance(x, Y)
        if isinstance(test, ast.Call):
            if isinstance(test.func, ast.Name) and test.func.id == "isinstance":
                return "type_check"

        # Anything else with a comparison operator
        if isinstance(test, ast.Compare):
            return "value_comparison"

        return "other"

    def _check_import_overlap(self, asserts: list[ast.Assert], func: ast.FunctionDef) -> ast.Assert | None:
        """Detect if the same function call appears on both sides of an assertion comparison."""
        for a in asserts:
            test = a.test
            if not isinstance(test, ast.Compare) or len(test.ops) != 1:
                continue
            if not isinstance(test.ops[0], ast.Eq):
                continue
            left = test.left
            right = test.comparators[0]
            if isinstance(left, ast.Call) and isinstance(right, ast.Call):
                left_name = self._call_name(left)
                right_name = self._call_name(right)
                if left_name and left_name == right_name:
                    return a
        return None

    @staticmethod
    def _call_name(node: ast.Call) -> str | None:
        """Extract the callable name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None
