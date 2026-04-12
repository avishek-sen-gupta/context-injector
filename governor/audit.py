"""Audit trail writer for governor evaluations.

Writes one JSON object per line (JSONL) to .claude/audit/<session-id>.jsonl.
"""

import json
import os


def write_audit_entry(path: str, entry: dict) -> None:
    """Append *entry* as a single JSON line to *path*."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_audit_log(path: str) -> list[dict]:
    """Read all entries from a JSONL audit log. Return [] if file missing."""
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
