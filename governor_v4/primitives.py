"""Tool blocking and capture rule matching."""

import fnmatch


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


def match_capture_rule(tool_name: str, tool_arg: str, tool_pattern: str) -> bool:
    """Check if a tool call matches a capture rule pattern like 'Bash(pytest*)'.

    Uses the same ToolName(arg_glob) syntax as exception patterns.
    """
    if "(" not in tool_pattern or not tool_pattern.endswith(")"):
        return fnmatch.fnmatch(tool_name, tool_pattern)
    pat_name, pat_arg = tool_pattern.rstrip(")").split("(", 1)
    return fnmatch.fnmatch(tool_name, pat_name) and fnmatch.fnmatch(tool_arg, pat_arg)
