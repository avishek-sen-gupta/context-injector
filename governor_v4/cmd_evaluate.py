"""PreToolUse handler: evaluate tool call against current phase."""

import json
import sys

from governor_v4.cli import load_engine


def run_evaluate(session_id: str, hook_input: dict) -> str | None:
    """Evaluate a tool call. Returns block JSON or None (allow)."""
    engine = load_engine(session_id)
    if not engine:
        return None

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    result = engine.evaluate(tool_name, tool_input)
    if result["action"] == "block":
        return json.dumps({
            "decision": "block",
            "reason": result["message"],
        })
    return None


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 evaluate`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    hook_input = json.loads(sys.stdin.read())
    output = run_evaluate(session_id, hook_input)
    if output:
        print(output)
