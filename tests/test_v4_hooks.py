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


class TestFullCycle:
    """End-to-end test: activate → block → capture → transition → verify."""

    def test_tdd_cycle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(REPO_ROOT, "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cli import load_engine, is_governor_active
        from governor_v4.cmd_prompt import run_prompt
        from governor_v4.cmd_evaluate import run_evaluate
        from governor_v4.cmd_capture import run_capture

        # 1. Activate
        output = run_prompt("s1", "/governor tdd")
        assert "writing_tests" in json.loads(output)["hookSpecificOutput"]["additionalContext"]

        # 2. Block production write
        output = run_evaluate("s1", {"tool_name": "Write", "tool_input": {"file_path": "main.py"}})
        assert output is not None
        assert json.loads(output)["decision"] == "block"

        # 3. Allow test write
        output = run_evaluate("s1", {"tool_name": "Write", "tool_input": {"file_path": "test_foo.py"}})
        assert output is None  # allowed

        # 4. Capture pytest output
        output = run_capture("s1", {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_output": "FAILED 1 test",
            "tool_exit_code": 1,
        })
        assert output is not None
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        key = [w for w in ctx.split() if w.startswith("evt_")][0]

        # 5. Transition to fixing_tests
        output = run_prompt("s1", f"/governor transition fixing_tests {key}")
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        assert "fixing_tests" in ctx

        # 6. Verify production write now allowed
        output = run_evaluate("s1", {"tool_name": "Write", "tool_input": {"file_path": "main.py"}})
        assert output is None  # allowed in fixing_tests

        # 7. Status check
        output = run_prompt("s1", "/governor status")
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        assert "fixing_tests" in ctx

        # 8. Evidence check
        output = run_prompt("s1", "/governor evidence")
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        assert key in ctx

        # 9. Deactivate
        output = run_prompt("s1", "/governor off")
        assert not is_governor_active("s1")
