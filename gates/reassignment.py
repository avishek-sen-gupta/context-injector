# gates/reassignment.py
"""ReassignmentGate adapter — wraps python-fp-lint's ReassignmentGate for the governor gate protocol."""

import os
import sys

from gates.base import Gate, GateContext, GateResult, GateVerdict

# Ensure python-fp-lint submodule is importable
_lint_pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "lint")
if _lint_pkg not in sys.path:
    sys.path.insert(0, _lint_pkg)

from python_fp_lint import ReassignmentGate as _ReassignmentGate


class ReassignmentGate(Gate):
    """Gate adapter that delegates to python-fp-lint's ReassignmentGate."""

    name = "reassignment"

    def evaluate(self, ctx: GateContext) -> GateResult:
        result = _ReassignmentGate().evaluate(ctx.recent_files, ctx.project_root)
        if result.passed:
            return GateResult(GateVerdict.PASS)
        return GateResult(
            GateVerdict.FAIL,
            message=self._format_violations(result.violations),
            issues=[f"{v.rule}:{v.file}:{v.line}" for v in result.violations],
        )

    @staticmethod
    def _format_violations(violations) -> str:
        lines = [f"GATE: reassignment — {len(violations)} violation(s) found:"]
        for v in violations:
            lines.append(
                f"  - '{v.message}' at {v.file}:{v.line}"
            )
        lines.append("")
        lines.append("Use immutable patterns — avoid rebinding variables.")
        return "\n".join(lines)
