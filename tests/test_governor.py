import json
import os

import pytest

from governor.governor import Governor
from machines.tdd_cycle import TDDCycle


@pytest.fixture
def governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=TDDCycle(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


class TestBasicEvaluation:
    def test_evaluate_returns_current_state(self, governor):
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["current_state"] == "red"
        assert result["action"] in ("allow", "remind", "challenge", "block")

    def test_no_transition_when_tool_matches_state(self, governor):
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["transition"] is None
        assert result["action"] == "allow"

    def test_challenge_when_tool_mismatches_state(self, governor):
        # In red state, editing a source file (not test) should challenge
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/src/auth.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert result["message"] is not None


class TestDeclarePhase:
    def test_declaration_triggers_transition(self, governor):
        # Satisfy precondition: write a test file first
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T11:59:00Z",
        })
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["transition"] == "red -> green"
        assert result["action"] == "allow"
        assert result["current_state"] == "green"

    def test_invalid_declaration_is_challenged(self, governor):
        # Can't go to refactor from red
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "refactor", "reason": "skip ahead"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert result["transition"] is None


class TestGraduatedResponse:
    def test_high_softness_allows_silently(self, governor):
        # test_written is softness 1.0 — satisfy precondition first
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T11:59:00Z",
        })
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "allow"
        assert result["message"] is None

    def test_low_softness_challenges(self, governor):
        # need_docs is softness 0.2
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "docs_detour", "reason": "docs are wrong"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert result["message"] is not None


class TestContextInjection:
    def test_context_included_on_state_change(self, governor):
        # Satisfy precondition first
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T11:59:00Z",
        })
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert len(result["context_to_inject"]) > 0

    def test_context_skipped_when_state_unchanged(self, governor):
        # First call injects context
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        # Second call with same state skips injection
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_bar.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:01:00Z",
        })
        assert result["context_to_inject"] == []


class TestAuditTrail:
    def test_audit_entry_written(self, governor, tmp_audit_dir):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        audit_file = os.path.join(tmp_audit_dir, "test-session.audit.json")
        assert os.path.exists(audit_file)
        from governor.audit import read_audit_log
        entries = read_audit_log(audit_file)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry["machine"] == "TDDCycle"
        assert entry["from_state"] == "red"
        assert entry["tool_name"] == "Edit"


class TestPreconditions:
    def test_declaration_without_precondition_met_is_challenged(self, governor):
        """Declaring green without having written a test file should be challenged."""
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "skipping test"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert "precondition" in result["message"].lower() or "test" in result["message"].lower()
        # Should NOT have transitioned
        assert result["current_state"] == "red"

    def test_declaration_with_precondition_met_is_allowed(self, governor):
        """Declaring green after writing a test file should be allowed."""
        # First: write a test file (satisfies precondition)
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        # Now declare green
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:01:00Z",
        })
        assert result["action"] == "allow"
        assert result["current_state"] == "green"

    def test_recent_tools_reset_after_transition(self, governor):
        """After transitioning, recent tools should reset so the next
        transition requires fresh preconditions."""
        # Write test file, declare green
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:01:00Z",
        })
        # Now in green. Declare refactor without running pytest — should challenge
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "refactor", "reason": "tests pass"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:02:00Z",
        })
        assert result["action"] == "challenge"
        assert result["current_state"] == "green"

    def test_precondition_met_via_edit(self, governor):
        """Edit(test_*) should also satisfy the precondition for test_written."""
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_bar.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test written"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:01:00Z",
        })
        assert result["action"] == "allow"
        assert result["current_state"] == "green"

    def test_no_preconditions_still_allows(self, governor):
        """Transitions without preconditions should still work normally."""
        # Write test, go to green
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:01:00Z",
        })
        # Run pytest (satisfies test_passes precondition)
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/test_foo.py -v"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:02:00Z",
        })
        # Declare refactor — test_passes has precondition Bash(pytest*)
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "refactor", "reason": "tests pass"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:03:00Z",
        })
        assert result["action"] == "allow"
        assert result["current_state"] == "refactor"


class TestStatePersistence:
    def test_state_persisted_after_transition(self, governor, tmp_state_dir):
        # Satisfy precondition first
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T11:59:00Z",
        })
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        state_file = os.path.join(tmp_state_dir, "testhash.json")
        with open(state_file) as f:
            state = json.load(f)
        assert state["inner_state"] == "green"


class TestToolSignatures:
    def test_write_tool_records_full_path(self, governor):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert any("/project/tests/test_foo.py" in t for t in governor._recent_tools)

    def test_edit_tool_records_full_path(self, governor):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/src/widget.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert any("/project/src/widget.py" in t for t in governor._recent_tools)

    def test_bash_tool_records_command(self, governor):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/ -v"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert any("pytest tests/ -v" in t for t in governor._recent_tools)
