# governor_v4/cli.py
"""CLI shared setup: state dirs, lock files, engine loading."""

import json
import os
import re
import shutil

from governor_v4.engine import GovernorV4
from governor_v4.loader import load_machine_from_json

_STATE_ROOT = "/tmp/ctx-governor"
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_session_id(session_id: str) -> None:
    """Reject empty or path-traversal-prone session IDs."""
    if not session_id or not _SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session ID: {session_id!r}")


def get_state_dir(session_id: str) -> str:
    """Return the state directory for a session."""
    _validate_session_id(session_id)
    return os.path.join(_STATE_ROOT, session_id)


def get_lock_file(session_id: str) -> str:
    """Return the lock file path for a session."""
    return os.path.join(get_state_dir(session_id), "active")


def is_governor_active(session_id: str) -> bool:
    """Check if governor is active for this session."""
    return os.path.exists(get_lock_file(session_id))


def activate_governor(session_id: str, machine_path: str) -> GovernorV4:
    """Create lock file, load machine, init engine, save state."""
    state_dir = get_state_dir(session_id)
    os.makedirs(state_dir, exist_ok=True)

    # Write lock file with machine path
    with open(get_lock_file(session_id), "w") as f:
        json.dump({"machine": machine_path}, f)

    config = load_machine_from_json(machine_path, from_file=True)
    engine = GovernorV4(
        config=config,
        session_id=session_id,
        state_dir=state_dir,
    )
    engine._save_phase()
    return engine


def deactivate_governor(session_id: str) -> None:
    """Remove lock file and state directory."""
    state_dir = get_state_dir(session_id)
    if os.path.exists(state_dir):
        shutil.rmtree(state_dir)


def load_engine(session_id: str) -> GovernorV4 | None:
    """Load engine from persisted state. Returns None if not active."""
    lock = get_lock_file(session_id)
    if not os.path.exists(lock):
        return None

    with open(lock) as f:
        data = json.load(f)

    machine_path = data["machine"]
    state_dir = get_state_dir(session_id)
    config = load_machine_from_json(machine_path, from_file=True)
    return GovernorV4(
        config=config,
        session_id=session_id,
        state_dir=state_dir,
    )
