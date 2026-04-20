import json
import pytest
from governor_v4.locker import EvidenceLocker


class TestStore:
    def test_store_returns_key(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/",
            output="FAILED test_foo.py",
            exit_code=1,
        )
        assert key.startswith("evt_")
        assert len(key) == 10  # evt_ + 6 hex chars

    def test_store_creates_file(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/",
            output="FAILED",
            exit_code=1,
        )
        path = tmp_path / "s1_evidence.json"
        assert path.exists()

    def test_stored_entry_has_correct_fields(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_auth.py",
            output="FAILED test_auth.py::test_login",
            exit_code=1,
        )
        entry = locker.retrieve(key)
        assert entry["type"] == "pytest_output"
        assert entry["tool_name"] == "Bash"
        assert entry["command"] == "pytest tests/test_auth.py"
        assert entry["output"] == "FAILED test_auth.py::test_login"
        assert entry["exit_code"] == 1
        assert "timestamp" in entry


class TestRetrieve:
    def test_retrieve_existing(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="PASSED",
        )
        entry = locker.retrieve(key)
        assert entry is not None
        assert entry["type"] == "pytest_output"

    def test_retrieve_missing_returns_none(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        assert locker.retrieve("evt_nonexistent") is None


class TestPersistence:
    def test_new_locker_reads_existing_file(self, tmp_path):
        locker1 = EvidenceLocker(str(tmp_path), "s1")
        key = locker1.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        # New locker instance loads from file
        locker2 = EvidenceLocker(str(tmp_path), "s1")
        entry = locker2.retrieve(key)
        assert entry is not None
        assert entry["type"] == "pytest_output"

    def test_different_sessions_isolated(self, tmp_path):
        locker1 = EvidenceLocker(str(tmp_path), "s1")
        key = locker1.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
        )
        locker2 = EvidenceLocker(str(tmp_path), "s2")
        assert locker2.retrieve(key) is None


class TestMultipleEntries:
    def test_multiple_stores_produce_unique_keys(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key1 = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_a.py",
            output="FAILED",
        )
        key2 = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_b.py",
            output="PASSED",
        )
        assert key1 != key2

    def test_keys_lists_all_stored(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        k1 = locker.store(evidence_type="a", tool_name="Bash", command="cmd1", output="out1")
        k2 = locker.store(evidence_type="b", tool_name="Bash", command="cmd2", output="out2")
        assert set(locker.keys()) == {k1, k2}
