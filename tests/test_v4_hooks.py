"""Integration tests for guvnah shell hook scripts."""

import json
import os
import subprocess
import sys
import pytest

HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks", "guvnah")
REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestShellHooks:
    def test_session_start_inactive_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "session-start.sh")],
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "nonexistent-test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_pre_tool_use_inactive_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "pre-tool-use.sh")],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "x.py"}}),
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "nonexistent-test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_post_tool_use_inactive_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "post-tool-use.sh")],
            input=json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "pytest"},
                "tool_output": "PASSED",
            }),
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "nonexistent-test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_user_prompt_no_command_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "user-prompt-submit.sh")],
            input=json.dumps({"prompt": "just a normal prompt"}),
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_hooks_are_executable(self):
        for name in ["session-start.sh", "pre-tool-use.sh", "post-tool-use.sh", "user-prompt-submit.sh"]:
            path = os.path.join(HOOKS_DIR, name)
            assert os.access(path, os.X_OK), f"{name} is not executable"
