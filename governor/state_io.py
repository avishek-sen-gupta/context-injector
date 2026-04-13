"""Read and write governor state files.

State files are JSON documents stored at .claude/state/<project-hash>.json.
They track which state machine is active, the current state, the deviation
stack, and when context was last injected.
"""

import json
import os


def default_state(session_id: str = "") -> dict:
    """Return a blank state dict with all required fields."""
    return {
        "outer_machine": None,
        "outer_state": None,
        "inner_machine": None,
        "inner_state": None,
        "stack": [],
        "last_injected_state": None,
        "last_injection_timestamp": None,
        "session_id": session_id,
        "gate_attempts": {},
    }


def load_state(path: str, session_id: str = "") -> dict:
    """Load state from *path*. Return default_state if file is missing."""
    if not os.path.exists(path):
        return default_state(session_id=session_id)
    with open(path, "r") as f:
        return json.load(f)


def save_state(path: str, state: dict) -> None:
    """Write *state* to *path*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
