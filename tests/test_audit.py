import json
import os

from governor.audit import write_audit_entry, read_audit_log


def test_write_creates_file_and_appends(tmp_audit_dir):
    log_file = os.path.join(tmp_audit_dir, "session-1.jsonl")

    entry1 = {
        "timestamp": "2026-04-12T12:00:00Z",
        "session_id": "session-1",
        "machine": "tdd-cycle",
        "from_state": "red",
        "to_state": "green",
        "trigger": "declaration",
        "softness": 1.0,
        "action_taken": "allow",
        "tool_name": "Bash",
        "tool_input_summary": "pytest tests/",
        "declaration": "test failing",
        "stack_depth": 0,
        "user_prompt": False,
        "context_injected": ["conditional/testing-patterns.md"],
        "message": None,
    }
    entry2 = {**entry1, "from_state": "green", "to_state": "refactor"}

    write_audit_entry(log_file, entry1)
    write_audit_entry(log_file, entry2)

    entries = read_audit_log(log_file)
    assert len(entries) == 2
    assert entries[0]["from_state"] == "red"
    assert entries[1]["from_state"] == "green"


def test_write_creates_parent_directories(tmp_audit_dir):
    log_file = os.path.join(tmp_audit_dir, "nested", "session-2.jsonl")
    entry = {"timestamp": "2026-04-12T12:00:00Z", "session_id": "session-2"}
    write_audit_entry(log_file, entry)
    assert os.path.exists(log_file)


def test_read_returns_empty_for_missing_file(tmp_audit_dir):
    log_file = os.path.join(tmp_audit_dir, "nonexistent.jsonl")
    entries = read_audit_log(log_file)
    assert entries == []
