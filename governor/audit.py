"""Audit trail for governor evaluations.

Uses TinyDB as a queryable document store. One database file per session.
"""

import os

from tinydb import TinyDB, where


class AuditStore:
    """Queryable audit trail backed by TinyDB."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = TinyDB(db_path)

    def write(self, entry: dict) -> int:
        """Append an audit document. Returns the document ID."""
        return self.db.insert(entry)

    def query(self, **filters) -> list[dict]:
        """Query audit entries by field values."""
        q = None
        for key, value in filters.items():
            condition = where(key) == value
            q = condition if q is None else q & condition
        return self.db.search(q) if q else self.db.all()

    def gate_failures(self, gate_name: str | None = None, since: str | None = None) -> list[dict]:
        """Query gate evaluations with non-pass verdicts."""
        q = (where("type") == "gate_eval") & (where("verdict") != "pass")
        if gate_name:
            q = q & (where("gate") == gate_name)
        if since:
            q = q & (where("timestamp") >= since)
        return self.db.search(q)


def write_audit_entry(path: str, entry: dict) -> None:
    """Append an audit entry. Backward-compatible function signature."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = TinyDB(path)
    db.insert(entry)


def read_audit_log(path: str) -> list[dict]:
    """Read all entries from an audit log. Return [] if file missing."""
    if not os.path.exists(path):
        return []
    db = TinyDB(path)
    return db.all()
