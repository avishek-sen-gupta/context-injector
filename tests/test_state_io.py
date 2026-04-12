import json
import os

from governor.state_io import load_state, save_state, default_state


def test_default_state_has_required_fields():
    state = default_state(session_id="s1")
    assert state["outer_machine"] is None
    assert state["outer_state"] is None
    assert state["inner_machine"] is None
    assert state["inner_state"] is None
    assert state["stack"] == []
    assert state["last_injected_state"] is None
    assert state["last_injection_timestamp"] is None
    assert state["session_id"] == "s1"


def test_save_and_load_roundtrip(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "test-project.json")
    state = default_state(session_id="s1")
    state["inner_machine"] = "tdd-cycle"
    state["inner_state"] = "red"

    save_state(state_file, state)
    loaded = load_state(state_file)

    assert loaded["inner_machine"] == "tdd-cycle"
    assert loaded["inner_state"] == "red"
    assert loaded["session_id"] == "s1"


def test_load_returns_default_when_missing(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "nonexistent.json")
    loaded = load_state(state_file, session_id="s2")
    assert loaded["session_id"] == "s2"
    assert loaded["inner_state"] is None


def test_save_creates_parent_directories(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "nested", "deep", "state.json")
    state = default_state(session_id="s3")
    save_state(state_file, state)
    assert os.path.exists(state_file)


def test_save_overwrites_existing(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "overwrite.json")
    save_state(state_file, default_state(session_id="s1"))
    save_state(state_file, default_state(session_id="s2"))
    loaded = load_state(state_file)
    assert loaded["session_id"] == "s2"
