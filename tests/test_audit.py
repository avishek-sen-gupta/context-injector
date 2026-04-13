import os
import pytest

from governor.audit import AuditStore, write_audit_entry, read_audit_log


class TestAuditStore:
    def test_write_returns_doc_id(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        doc_id = store.write({"timestamp": "2026-04-13T12:00:00Z", "type": "transition"})
        assert isinstance(doc_id, int)

    def test_write_and_query_all(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "transition", "from_state": "red"})
        store.write({"type": "transition", "from_state": "green"})
        results = store.query()
        assert len(results) == 2

    def test_query_with_filter(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "transition", "from_state": "red"})
        store.write({"type": "gate_eval", "gate": "test_quality"})
        results = store.query(type="gate_eval")
        assert len(results) == 1
        assert results[0]["gate"] == "test_quality"

    def test_gate_failures_filters_non_pass(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "pass"})
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "fail"})
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "review"})
        results = store.gate_failures()
        assert len(results) == 2

    def test_gate_failures_filters_by_gate_name(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "fail"})
        store.write({"type": "gate_eval", "gate": "diff_size", "verdict": "fail"})
        results = store.gate_failures(gate_name="test_quality")
        assert len(results) == 1

    def test_gate_failures_filters_by_since(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "gate_eval", "gate": "tq", "verdict": "fail", "timestamp": "2026-04-12T10:00:00Z"})
        store.write({"type": "gate_eval", "gate": "tq", "verdict": "fail", "timestamp": "2026-04-13T10:00:00Z"})
        results = store.gate_failures(since="2026-04-13T00:00:00Z")
        assert len(results) == 1


class TestBackwardCompatFunctions:
    def test_write_audit_entry_creates_file(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "session.audit.json")
        entry = {"timestamp": "2026-04-13T12:00:00Z", "type": "transition"}
        write_audit_entry(db_path, entry)
        assert os.path.exists(db_path)

    def test_write_and_read_audit_log(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "session.audit.json")
        write_audit_entry(db_path, {"type": "transition", "from_state": "red"})
        write_audit_entry(db_path, {"type": "transition", "from_state": "green"})
        entries = read_audit_log(db_path)
        assert len(entries) == 2
        assert entries[0]["from_state"] == "red"

    def test_read_returns_empty_for_missing_file(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "nonexistent.audit.json")
        entries = read_audit_log(db_path)
        assert entries == []

    def test_write_creates_parent_directories(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "nested", "session.audit.json")
        write_audit_entry(db_path, {"timestamp": "2026-04-13T12:00:00Z"})
        assert os.path.exists(db_path)
