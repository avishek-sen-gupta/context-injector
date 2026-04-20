"""CLI entry point: python3 -m governor_v4 <subcommand>."""

import sys


def main():
    if len(sys.argv) < 2:
        print("usage: python3 -m governor_v4 <init|evaluate|capture|prompt>", file=sys.stderr)
        sys.exit(1)

    subcommand = sys.argv[1]

    if subcommand == "init":
        from governor_v4.cmd_init import run
        run(sys.argv[2:])
    elif subcommand == "evaluate":
        from governor_v4.cmd_evaluate import run
        run(sys.argv[2:])
    elif subcommand == "capture":
        from governor_v4.cmd_capture import run
        run(sys.argv[2:])
    elif subcommand == "prompt":
        from governor_v4.cmd_prompt import run
        run(sys.argv[2:])
    else:
        print(f"unknown subcommand: {subcommand}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
