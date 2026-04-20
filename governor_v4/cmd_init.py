"""SessionStart handler: restore engine state and inject phase context."""

import json
import sys

from governor_v4.cli import load_engine, is_governor_active


def run_init(session_id: str) -> str | None:
    """Restore engine and return hook JSON with phase context, or None if inactive."""
    if not is_governor_active(session_id):
        return None

    engine = load_engine(session_id)
    if not engine:
        return None

    node = engine._get_node()
    blocked = node.blocked_tools or []
    exceptions = node.allowed_exceptions or []

    ctx_parts = [f"Governor active: phase={engine.current_phase}"]
    if blocked:
        ctx_parts.append(f"Blocked tools: {', '.join(blocked)}")
    if exceptions:
        ctx_parts.append(f"Exceptions: {', '.join(exceptions)}")

    ctx = ". ".join(ctx_parts) + "."

    return json.dumps({
        "hookSpecificOutput": {
            "additionalContext": ctx,
        }
    })


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 init`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    output = run_init(session_id)
    if output:
        print(output)
