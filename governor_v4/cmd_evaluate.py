"""PreToolUse handler: evaluate tool call against current phase."""

import json

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
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": result["message"],
            },
        })
    return None


