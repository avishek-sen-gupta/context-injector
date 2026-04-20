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

    @pytest.mark.skip(reason="cmd_prompt not yet implemented (Task 6)")
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
