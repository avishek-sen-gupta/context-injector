"""UserPromptSubmit handler: parse /governor commands."""

import json
import os
import sys

from governor_v4.cli import (
    activate_governor,
    deactivate_governor,
    is_governor_active,
    load_engine,
)

_MACHINE_DIR = os.environ.get(
    "GUVNAH_MACHINES",
    os.path.expanduser("~/.claude/plugins/guvnah/machines"),
)


def _hook_output(ctx: str) -> str:
    return json.dumps({"hookSpecificOutput": {"additionalContext": ctx}})


def _available_machines() -> list[str]:
    if not os.path.isdir(_MACHINE_DIR):
        return []
    return [
        f.removesuffix(".json")
        for f in os.listdir(_MACHINE_DIR)
        if f.endswith(".json")
    ]


def run_prompt(session_id: str, prompt: str) -> str | None:
    """Parse /governor command from prompt. Returns hook JSON or None."""
    line = None
    for l in prompt.splitlines():
        stripped = l.strip()
        if stripped.startswith("/governor"):
            line = stripped
            break

    if not line:
        return None

    parts = line.split()
    if len(parts) < 2:
        return _hook_output("Usage: /governor <machine|off|status|transition|evidence>")

    subcmd = parts[1]

    if subcmd == "off":
        deactivate_governor(session_id)
        return _hook_output("Governor deactivated.")

    if subcmd == "status":
        engine = load_engine(session_id)
        if not engine:
            return _hook_output("Governor is not active.")
        node = engine._get_node()
        edges = [e for e in engine.config.edges if e.from_state == engine.current_phase]
        targets = [e.to_state for e in edges]
        blocked = node.blocked_tools or []
        ctx = (
            f"Phase: {engine.current_phase}. "
            f"Blocked: {', '.join(blocked) if blocked else 'none'}. "
            f"Available transitions: {', '.join(targets) if targets else 'none'}."
        )
        return _hook_output(ctx)

    if subcmd == "transition":
        if len(parts) < 3:
            return _hook_output("Usage: /governor transition <target> [evidence_key]")
        target = parts[2]
        evidence_key = parts[3] if len(parts) > 3 else None
        engine = load_engine(session_id)
        if not engine:
            return _hook_output("Governor is not active.")
        result = engine.want_to_transition(target, evidence_key)
        if result["action"] == "allow":
            node = engine._get_node()
            blocked = node.blocked_tools or []
            ctx = (
                f"Transition allowed: {result['from_state']} -> {result['to_state']}. "
                f"Now in {engine.current_phase}. "
                f"Blocked: {', '.join(blocked) if blocked else 'none'}."
            )
        else:
            ctx = f"Transition denied: {result['message']}"
        return _hook_output(ctx)

    if subcmd == "evidence":
        engine = load_engine(session_id)
        if not engine:
            return _hook_output("Governor is not active.")
        if not engine.locker:
            return _hook_output("No evidence locker configured.")
        keys = engine.locker.keys()
        if not keys:
            return _hook_output("Evidence locker is empty.")
        lines = []
        for key in keys:
            entry = engine.locker.retrieve(key)
            if entry:
                lines.append(
                    f"  {key}: type={entry['type']}, tool={entry['tool_name']}, "
                    f"time={entry['timestamp']}"
                )
        ctx = "Evidence locker:\n" + "\n".join(lines)
        return _hook_output(ctx)

    # Treat as machine name: /governor tdd
    machine_name = subcmd
    machine_path = os.path.join(_MACHINE_DIR, f"{machine_name}.json")
    if not os.path.exists(machine_path):
        available = _available_machines()
        ctx = (
            f"Machine '{machine_name}' not found. "
            f"Available: {', '.join(available) if available else 'none'}."
        )
        return _hook_output(ctx)

    engine = activate_governor(session_id, machine_path)
    node = engine._get_node()
    blocked = node.blocked_tools or []
    ctx = (
        f"Governor activated: machine={engine.config.name}, "
        f"phase={engine.current_phase}. "
        f"Blocked: {', '.join(blocked) if blocked else 'none'}."
    )
    return _hook_output(ctx)


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 prompt`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    try:
        stdin_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return  # fail open — no command to parse
    prompt = stdin_data.get("prompt", "")
    output = run_prompt(session_id, prompt)
    if output:
        print(output)
