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

    from governor_v4.cmd_prompt import _describe_blocking

    node = engine._get_node()
    ctx = f"Governor active: phase={engine.current_phase}. {_describe_blocking(node)}"

    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
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
