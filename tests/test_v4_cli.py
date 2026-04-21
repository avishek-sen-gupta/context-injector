# tests/test_v4_cli.py
import json
import os
import pytest
from governor_v4.cli import (
    get_state_dir,
    get_lock_file,
    is_governor_active,
    activate_governor,
    deactivate_governor,
    load_engine,
)
from governor_v4.primitives import match_capture_rule


class TestSessionIdValidation:
    def test_valid_alphanumeric(self):
        get_state_dir("abc123")  # should not raise

    def test_valid_with_dashes_underscores(self):
        get_state_dir("my-session_01")  # should not raise

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Invalid session ID"):
            get_state_dir("")

    def test_slash_raises(self):
        with pytest.raises(ValueError, match="Invalid session ID"):
            get_state_dir("../../etc")

    def test_dot_dot_raises(self):
        with pytest.raises(ValueError, match="Invalid session ID"):
            get_state_dir("test/../escape")

    def test_space_raises(self):
        with pytest.raises(ValueError, match="Invalid session ID"):
            get_state_dir("has space")


class TestStateDir:
    def test_state_dir_uses_session_hash(self):
        d = get_state_dir("abc123")
        assert d == "/tmp/ctx-governor/abc123"

    def test_state_dir_different_sessions(self):
        assert get_state_dir("a") != get_state_dir("b")


class TestLockFile:
    def test_lock_file_path(self):
        path = get_lock_file("abc123")
        assert path == "/tmp/ctx-governor/abc123/active"


class TestActivateDeactivate:
    def test_activate_creates_lock_and_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        lock = os.path.join(str(tmp_path), session_id, "active")
        assert os.path.exists(lock)
        # Lock file contains machine path
        with open(lock) as f:
            data = json.load(f)
        assert data["machine"] == machine_path

    def test_deactivate_removes_lock_and_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        deactivate_governor(session_id)
        lock = os.path.join(str(tmp_path), session_id, "active")
        assert not os.path.exists(lock)

    def test_is_active_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        assert is_governor_active(session_id) is True

    def test_is_active_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        assert is_governor_active("nonexistent") is False


class TestLoadEngine:
    def test_load_engine_returns_governor(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        engine = load_engine(session_id)
        assert engine is not None
        assert engine.current_phase == "writing_tests"

    def test_load_engine_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        engine = load_engine("nonexistent")
        assert engine is None

    def test_load_engine_restores_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        # Transition from fixing_tests to writing_tests (which has no evidence_contract)
        engine1 = load_engine(session_id)
        # Manually advance to fixing_tests first
        engine1._current_phase = "fixing_tests"
        engine1._save_phase()
        # Now transition to writing_tests (no evidence contract needed)
        engine1.want_to_transition("writing_tests", None)
        # Reload — should restore
        engine2 = load_engine(session_id)
        assert engine2.current_phase == "writing_tests"


class TestMainDispatch:
    def test_no_args_prints_usage(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "governor_v4"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "usage" in result.stderr.lower()

    def test_unknown_subcommand_fails(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "governor_v4", "bogus"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_prompt_subcommand_exists(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "governor_v4", "prompt", "--session", "test"],
            input='{"prompt": "hello"}',
            capture_output=True,
            text=True,
        )
        # Should exit 0 — no /governor command in "hello"
        assert result.returncode == 0


class TestCmdInit:
    def test_init_restore_active_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_init import run_init
        output = run_init("s1")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "writing_tests" in ctx

    def test_init_restore_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_init import run_init
        output = run_init("nonexistent")
        assert output is None

    def test_init_restore_includes_phase_and_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_init import run_init
        output = run_init("s1")
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "blocked" in ctx.lower() or "Write" in ctx


class TestCmdEvaluate:
    def test_evaluate_allow(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Read", "tool_input": {"file_path": "main.py"}}
        output = run_evaluate("s1", hook_input)
        assert output is None  # allow = no output

    def test_evaluate_block(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Write", "tool_input": {"file_path": "main.py"}}
        output = run_evaluate("s1", hook_input)
        assert output is not None
        parsed = json.loads(output)
        assert parsed["decision"] == "block"
        assert "blocked" in parsed["reason"].lower()

    def test_evaluate_exception_allows(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Write", "tool_input": {"file_path": "test_foo.py"}}
        output = run_evaluate("s1", hook_input)
        assert output is None  # exception allows it

    def test_evaluate_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Write", "tool_input": {"file_path": "main.py"}}
        output = run_evaluate("nonexistent", hook_input)
        assert output is None  # inactive = pass-through


class TestCmdCapture:
    def test_capture_matching_tool(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_response": {"output": "FAILED 2 tests", "exit_code": 1},
        }
        output = run_capture("s1", hook_input)
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "evt_" in ctx

    def test_capture_non_matching_tool(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "main.py"},
            "tool_response": "file contents",
        }
        output = run_capture("s1", hook_input)
        assert output is None  # no capture rule matched

    def test_capture_stores_in_locker(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_response": {"output": "PASSED 5 tests", "exit_code": 0},
        }
        output = run_capture("s1", hook_input)
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        # Extract key from context
        key = [w for w in ctx.split() if w.startswith("evt_")][0]

        # Verify it's in the locker
        engine = load_engine("s1")
        entry = engine.locker.retrieve(key)
        assert entry is not None
        assert entry["type"] == "pytest_output"
        assert entry["output"] == "PASSED 5 tests"
        assert entry["exit_code"] == 0

    def test_capture_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "tool_response": {"output": "output", "exit_code": 0},
        }
        output = run_capture("nonexistent", hook_input)
        assert output is None


class TestCmdPrompt:
    def test_no_governor_command_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_prompt import run_prompt
        output = run_prompt("s1", "just a normal prompt")
        assert output is None

    def test_governor_start_activates(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        output = run_prompt("s1", "/governor tdd")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "writing_tests" in ctx
        assert is_governor_active("s1")

    def test_governor_off_deactivates(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        output = run_prompt("s1", "/governor off")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "deactivated" in ctx.lower()
        assert not is_governor_active("s1")

    def test_governor_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        output = run_prompt("s1", "/governor status")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "writing_tests" in ctx
        assert "fixing_tests" in ctx  # available transition target

    def test_governor_transition(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        # Activate and store some evidence
        run_prompt("s1", "/governor tdd")
        engine = load_engine("s1")
        key = engine.locker.store("pytest_output", "Bash", "pytest", "FAILED", 1)

        output = run_prompt("s1", f"/governor transition fixing_tests {key}")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "fixing_tests" in ctx

    def test_governor_transition_denied(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        # No evidence — should deny
        output = run_prompt("s1", "/governor transition fixing_tests")
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "deny" in ctx.lower() or "require" in ctx.lower()

    def test_governor_evidence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        engine = load_engine("s1")
        key = engine.locker.store("pytest_output", "Bash", "pytest", "FAILED", 1)

        output = run_prompt("s1", "/governor evidence")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert key in ctx
        assert "pytest_output" in ctx

    def test_governor_unknown_machine(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        output = run_prompt("s1", "/governor nonexistent")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "not found" in ctx.lower()
