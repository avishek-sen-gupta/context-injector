"""CLI entry point: python3 -m governor_v4 <subcommand>."""

import json
import sys


def parse_session(args: list[str]) -> str:
    """Extract --session value from args, or exit with error."""
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            return args[i + 1]
    print("error: --session required", file=sys.stderr)
    sys.exit(1)


def read_stdin() -> dict | None:
    """Read and parse JSON from stdin, or return None on failure."""
    try:
        return json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return None


def main():
    if len(sys.argv) < 2:
        print("usage: python3 -m governor_v4 <init|evaluate|capture|prompt>", file=sys.stderr)
        sys.exit(1)

    subcommand = sys.argv[1]
    args = sys.argv[2:]
    session_id = parse_session(args)

    if subcommand == "init":
        from governor_v4.cmd_init import run_init
        output = run_init(session_id)

    elif subcommand == "evaluate":
        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = read_stdin()
        if not hook_input:
            return
        output = run_evaluate(session_id, hook_input)

    elif subcommand == "capture":
        from governor_v4.cmd_capture import run_capture
        hook_input = read_stdin()
        if not hook_input:
            return
        output = run_capture(session_id, hook_input)

    elif subcommand == "prompt":
        from governor_v4.cmd_prompt import run_prompt
        hook_input = read_stdin()
        if not hook_input:
            return
        prompt = hook_input.get("prompt", "")
        output = run_prompt(session_id, prompt)

    else:
        print(f"unknown subcommand: {subcommand}", file=sys.stderr)
        sys.exit(1)

    if output:
        print(output)


if __name__ == "__main__":
    main()
