"""Tool blocking, context injection, and gate registry."""

import fnmatch
from gates.lint import LintGate
from gates.reassignment import ReassignmentGate
from gates.test_quality import TestQualityGate


def check_tool_allowed(
    tool_name: str,
    tool_arg: str | None = None,
    blocked: list[str] | None = None,
    exceptions: list[str] | None = None,
) -> bool:
    """Check if a tool call is allowed given blocklist and exception patterns.

    Exception patterns use "ToolName(arg_glob)" syntax, e.g. "Write(test_*)".
    """
    if not blocked:
        return True

    tool_blocked = any(fnmatch.fnmatch(tool_name, p) for p in blocked)
    if not tool_blocked:
        return True

    if exceptions and tool_arg:
        for exc in exceptions:
            if "(" in exc and exc.endswith(")"):
                exc_name, exc_pattern = exc.rstrip(")").split("(", 1)
                if exc_name == tool_name and fnmatch.fnmatch(tool_arg, exc_pattern):
                    return True

    return False


GATE_REGISTRY: dict[str, type] = {
    "lint": LintGate,
    "reassignment": ReassignmentGate,
    "test_quality": TestQualityGate,
}
