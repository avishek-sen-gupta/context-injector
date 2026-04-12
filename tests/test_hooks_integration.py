import json
import os
import subprocess
import tempfile

import pytest


@pytest.fixture
def mock_project():
    """Create a temporary project directory with .claude structure."""
    with tempfile.TemporaryDirectory() as d:
        claude_dir = os.path.join(d, ".claude")
        os.makedirs(os.path.join(claude_dir, "core"))
        os.makedirs(os.path.join(claude_dir, "conditional"))
        with open(os.path.join(claude_dir, "core", "project.md"), "w") as f:
            f.write("# Test Project\n")
        with open(os.path.join(claude_dir, "conditional", "testing-patterns.md"), "w") as f:
            f.write("# Testing\n")
        yield d


def test_governor_cli_returns_json(mock_project):
    """Test that governor.py reads stdin JSON and writes stdout JSON."""
    event = {
        "event": "pre_tool_use",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/project/tests/test_foo.py"},
        "session_id": "integration-test",
        "timestamp": "2026-04-12T12:00:00Z",
    }

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "integration"
    env["CTX_MACHINE"] = "machines.tdd_cycle.TDDCycle"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", "-m", "governor"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    response = json.loads(result.stdout)
    assert response["current_state"] == "red"
    assert response["action"] in ("allow", "remind", "challenge", "block")


def test_governor_declaration_transition(mock_project):
    """Test that a DeclarePhase event triggers a state transition."""
    event = {
        "event": "pre_tool_use",
        "tool_name": "Bash",
        "tool_input": {
            "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
        },
        "session_id": "integration-test-2",
        "timestamp": "2026-04-12T12:00:00Z",
    }

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "integration2"
    env["CTX_MACHINE"] = "machines.tdd_cycle.TDDCycle"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", "-m", "governor"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    response = json.loads(result.stdout)
    assert response["current_state"] == "green"
    assert response["transition"] == "red -> green"


def test_full_tdd_cycle_sequence(mock_project):
    """Test a complete Red → Green → Refactor → Red cycle through the governor CLI."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_dir = os.path.join(mock_project, ".ctx-state")
    audit_dir = os.path.join(mock_project, ".ctx-audit")

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = state_dir
    env["CTX_AUDIT_DIR"] = audit_dir
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "e2e"
    env["CTX_MACHINE"] = "machines.tdd_cycle.TDDCycle"

    def run_event(event):
        result = subprocess.run(
            ["python3", "-m", "governor"],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return json.loads(result.stdout)

    # 1. Start in red — edit a test file (allowed)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Edit",
        "tool_input": {"file_path": "/p/tests/test_x.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:00:00Z",
    })
    assert r["current_state"] == "red"
    assert r["action"] == "allow"

    # 2. Declare green
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "green", "reason": "test failing"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:01:00Z",
    })
    assert r["current_state"] == "green"
    assert r["transition"] == "red -> green"

    # 3. Edit source file in green (allowed)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Edit",
        "tool_input": {"file_path": "/p/src/auth.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:02:00Z",
    })
    assert r["current_state"] == "green"
    assert r["action"] == "allow"

    # 4. Declare refactor
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "refactor", "reason": "tests pass"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:03:00Z",
    })
    assert r["current_state"] == "refactor"

    # 5. Declare back to red
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "red", "reason": "refactor done"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:04:00Z",
    })
    assert r["current_state"] == "red"

    # 6. Verify audit trail
    audit_file = os.path.join(audit_dir, "e2e.jsonl")
    assert os.path.exists(audit_file)
    with open(audit_file) as f:
        entries = [json.loads(line) for line in f if line.strip()]
    assert len(entries) == 5
    assert entries[0]["from_state"] == "red"
    assert entries[1]["to_state"] == "green"
    assert entries[4]["to_state"] == "red"
