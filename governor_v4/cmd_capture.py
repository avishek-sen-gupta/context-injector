"""PostToolUse handler: capture tool output as evidence."""

import json

from governor_v4.cli import load_engine
from governor_v4.primitives import match_capture_rule


def _parse_exit_code(error: str) -> int | None:
    """Extract exit code from PostToolUseFailure error string.

    Error strings start with 'Exit code N\\n...'
    """
    if error and error.startswith("Exit code "):
        first_line = error.split("\n", 1)[0]
        try:
            return int(first_line.removeprefix("Exit code "))
        except ValueError:
            pass
    return None


def run_capture(session_id: str, hook_input: dict) -> str | None:
    """Match capture rules and store evidence. Returns hook JSON or None."""
    engine = load_engine(session_id)
    if not engine or not engine.locker:
        return None

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    is_failure = hook_input.get("hook_event_name") == "PostToolUseFailure"

    if is_failure:
        # PostToolUseFailure: output is in "error" field, starts with "Exit code N\n"
        error = hook_input.get("error", "")
        exit_code = _parse_exit_code(error)
        # Strip the "Exit code N\n\n" prefix to get the actual output
        tool_output = error.split("\n", 2)[-1].lstrip("\n") if error else ""
    else:
        # PostToolUse: output is in tool_response
        tool_response = hook_input.get("tool_response", {})
        if isinstance(tool_response, dict):
            tool_output = tool_response.get("stdout", "")
        else:
            tool_output = str(tool_response) if tool_response else ""
        exit_code = 0

    # Get the tool arg for matching
    if tool_name == "Bash":
        tool_arg = tool_input.get("command", "")
    elif tool_name in ("Write", "Edit"):
        tool_arg = tool_input.get("file_path", "")
    else:
        tool_arg = ""

    # Check capture rules for current node
    node = engine._get_node()
    for rule in node.capture:
        if match_capture_rule(tool_name, tool_arg, rule.tool_pattern):
            key = engine.locker.store(
                evidence_type=rule.evidence_type,
                tool_name=tool_name,
                command=tool_arg,
                output=tool_output,
                exit_code=exit_code,
            )
            return json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": (
                            f"Evidence captured: {key} "
                            f"(type={rule.evidence_type}, phase={engine.current_phase}). "
                            f"Use '/governor transition <target> {key}' to request a state transition."
                        ),
                    }
                }
            )

    return None
