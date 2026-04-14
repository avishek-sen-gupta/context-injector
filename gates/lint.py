# gates/lint.py
"""LintGate adapter — wraps python-fp-lint's LintGate for the governor gate protocol."""

import os
import sys

from gates.base import Gate, GateContext, GateResult, GateVerdict

# Ensure python-fp-lint submodule is importable
_lint_pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "lint")
if _lint_pkg not in sys.path:
    sys.path.insert(0, _lint_pkg)

from python_fp_lint import LintGate as _LintGate


class LintGate(Gate):
    """Gate adapter that delegates to python-fp-lint's LintGate."""

    name = "lint"

    def __init__(self, rules_dir: str | None = None):
        self._lint = _LintGate(rules_dir=rules_dir)

    def evaluate(self, ctx: GateContext) -> GateResult:
        result = self._lint.evaluate(ctx.recent_files, ctx.project_root)
        if result.passed:
            return GateResult(GateVerdict.PASS)
        return GateResult(
            GateVerdict.FAIL,
            message=self._format_violations(result.violations),
            issues=[f"{v.rule}:{v.file}:{v.line}" for v in result.violations],
        )

    @staticmethod
    def _format_violations(violations) -> str:
        lines = [f"GATE: lint — {len(violations)} violation(s) found:"]
        for v in violations:
            lines.append(f"  - [{v.rule}] {v.file}:{v.line} — {v.message}")
        lines.append("")
        lines.append("Fix these lint violations before the transition can proceed.")
        return "\n".join(lines)
