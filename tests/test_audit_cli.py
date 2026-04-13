import json
import os
import subprocess


def test_audit_cli_returns_entries(tmp_path):
    """governor audit --all returns audit entries."""
    audit_dir = str(tmp_path)
    # Pre-populate an audit file
    from governor.audit import AuditStore
    store = AuditStore(os.path.join(audit_dir, "test-session.audit.json"))
    store.write({"type": "transition", "from_state": "writing_tests", "to_state": "red",
                 "timestamp": "2026-04-13T12:00:00Z", "session_id": "test-session"})

    result = subprocess.run(
        ["python3", "-m", "governor", "audit", "--all"],
        capture_output=True, text=True,
        env={**os.environ, "CTX_AUDIT_DIR": audit_dir, "PYTHONPATH": "."},
    )
    assert result.returncode == 0
    entries = json.loads(result.stdout)
    assert len(entries) >= 1
