"""PostToolUse handler: capture tool output as evidence."""

import json
import sys

from governor_v4.cli import load_engine
from governor_v4.primitives import match_capture_rule


def run_capture(session_id: str, hook_input: dict) -> str | None:
    """Match capture rules and store evidence. Returns hook JSON or None."""
    engine = load_engine(session_id)
    if not engine or not engine.locker:
        return None

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    tool_output = hook_input.get("tool_output", "")
    exit_code = hook_input.get("tool_exit_code")

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
            return json.dumps({
                "hookSpecificOutput": {
                    "additionalContext": (
                        f"Evidence captured: {key} "
                        f"(type={rule.evidence_type}, phase={engine.current_phase}). "
                        f"Use '/governor transition <target> {key}' to request a state transition."
                    ),
                }
            })

    return None


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 capture`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    hook_input = json.loads(sys.stdin.read())
    output = run_capture(session_id, hook_input)
    if output:
        print(output)
