"""Tests for the pipefail-guard PreToolUse hook."""

import json
import os
import subprocess

HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks", "guvnah")
HOOK = os.path.join(HOOKS_DIR, "pipefail-guard.sh")


def run_hook(tool_name, tool_input):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        ["bash", HOOK],
        input=payload, capture_output=True, text=True,
    )


class TestPipefailGuard:
    def test_prepends_pipefail_to_bash(self):
        result = run_hook("Bash", {"command": "pytest tests/"})
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "approve"
        assert parsed["tool_input"]["command"] == "set -o pipefail; pytest tests/"

    def test_skips_non_bash_tools(self):
        result = run_hook("Write", {"file_path": "x.py"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_skips_if_already_has_pipefail(self):
        result = run_hook("Bash", {"command": "set -o pipefail; pytest"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_hook_is_executable(self):
        assert os.access(HOOK, os.X_OK)

    def test_preserves_original_command(self):
        cmd = "git status && echo done"
        result = run_hook("Bash", {"command": cmd})
        parsed = json.loads(result.stdout)
        assert parsed["tool_input"]["command"].endswith(cmd)
