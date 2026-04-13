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
    """Test that a DeclarePhase event triggers a state transition (with precondition met)."""
    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "integration2"
    env["CTX_MACHINE"] = "machines.tdd_cycle.TDDCycle"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

    # First: write a test file to satisfy precondition
    run_event({
        "event": "pre_tool_use",
        "tool_name": "Write",
        "tool_input": {"file_path": "/project/tests/test_foo.py"},
        "session_id": "integration-test-2",
        "timestamp": "2026-04-12T11:59:00Z",
    })

    # Now declare green
    response = run_event({
        "event": "pre_tool_use",
        "tool_name": "Bash",
        "tool_input": {
            "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
        },
        "session_id": "integration-test-2",
        "timestamp": "2026-04-12T12:00:00Z",
    })

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

    # 1. Start in red — write a test file (allowed, satisfies precondition)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Write",
        "tool_input": {"file_path": "/p/tests/test_x.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:00:00Z",
    })
    assert r["current_state"] == "red"
    assert r["action"] == "allow"

    # 2. Declare green (precondition: test file written above)
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

    # 3b. Run pytest (satisfies precondition for test_passes)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/ -v"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:02:30Z",
    })
    assert r["current_state"] == "green"

    # 4. Declare refactor (precondition: pytest run above)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "refactor", "reason": "tests pass"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:03:00Z",
    })
    assert r["current_state"] == "refactor"

    # 4b. Edit a file (satisfies precondition for refactor_done)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Edit",
        "tool_input": {"file_path": "/p/src/auth.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:03:30Z",
    })
    assert r["current_state"] == "refactor"

    # 5. Declare back to red (precondition: edit above)
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
    assert len(entries) == 7
    assert entries[0]["from_state"] == "red"
    assert entries[1]["to_state"] == "green"
    assert entries[6]["to_state"] == "red"


def test_session_instructions_cli(mock_project):
    """Test that 'python3 -m governor session-instructions' outputs machine instructions."""
    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "instr-test"
    env["CTX_MACHINE"] = "machines.tdd.TDD"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", "-m", "governor", "session-instructions"],
        input='{"session_id":"test"}',
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "TDD Governor" in result.stdout
    assert "writing_tests" in result.stdout


def test_session_instructions_cli_different_machine(mock_project):
    """Test that session-instructions returns the correct machine's instructions."""
    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "instr-test2"
    env["CTX_MACHINE"] = "machines.feature_development.FeatureDevelopment"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", "-m", "governor", "session-instructions"],
        input='{"session_id":"test"}',
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Feature Development" in result.stdout
    assert "planning" in result.stdout


def test_status_cli_inactive(mock_project):
    """Test that 'python3 -m governor status' reports inactive when no lock file."""
    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_PROJECT_HASH"] = "status-test-inactive"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", "-m", "governor", "status"],
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    status = json.loads(result.stdout)
    assert status["active"] is False


def test_status_cli_active(mock_project):
    """Test that 'python3 -m governor status' reports machine and state when active."""
    env = os.environ.copy()
    state_dir = os.path.join(mock_project, ".ctx-state")
    governor_dir = os.path.join(mock_project, ".ctx-governor")
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(governor_dir, exist_ok=True)

    project_hash = "status-test-active"
    env["CTX_STATE_DIR"] = state_dir
    env["CTX_PROJECT_HASH"] = project_hash

    # Create lock file
    with open(os.path.join(governor_dir, project_hash), "w") as f:
        pass

    # Create machine file
    with open(os.path.join(state_dir, f"{project_hash}.machine"), "w") as f:
        f.write("machines.tdd.TDD")

    # Create state file
    with open(os.path.join(state_dir, f"{project_hash}.json"), "w") as f:
        json.dump({
            "inner_machine": "TDD",
            "inner_state": "fixing_tests",
            "session_id": "test-session",
            "last_injection_timestamp": "2026-04-13T12:00:00Z",
        }, f)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    env["CTX_GOVERNOR_DIR"] = governor_dir

    result = subprocess.run(
        ["python3", "-m", "governor", "status"],
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    status = json.loads(result.stdout)
    assert status["active"] is True
    assert status["machine"] == "machines.tdd.TDD"
    assert status["state"] == "fixing_tests"
    assert status["session_id"] == "test-session"


def test_context_cli_returns_resolved_files(mock_project):
    """Test that 'python3 -m governor context' returns resolved context file paths."""
    env = os.environ.copy()
    state_dir = os.path.join(mock_project, ".ctx-state")
    context_dir = os.path.join(mock_project, ".claude")
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(os.path.join(context_dir, "core"), exist_ok=True)

    project_hash = "context-test"
    env["CTX_STATE_DIR"] = state_dir
    env["CTX_PROJECT_HASH"] = project_hash
    env["CTX_CONTEXT_DIR"] = context_dir

    # Create machine file (TDD machine)
    with open(os.path.join(state_dir, f"{project_hash}.machine"), "w") as f:
        f.write("machines.tdd.TDD")

    # Create state file in fixing_tests state (CONTEXT maps to ["core/*"])
    with open(os.path.join(state_dir, f"{project_hash}.json"), "w") as f:
        json.dump({
            "inner_machine": "TDD",
            "inner_state": "fixing_tests",
            "session_id": "test-session",
        }, f)

    # Create context files that match "core/*"
    with open(os.path.join(context_dir, "core", "workflow.md"), "w") as f:
        f.write("# Workflow")
    with open(os.path.join(context_dir, "core", "project.md"), "w") as f:
        f.write("# Project")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", "-m", "governor", "context"],
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    paths = result.stdout.strip().splitlines()
    assert len(paths) == 2
    assert any("workflow.md" in p for p in paths)
    assert any("project.md" in p for p in paths)


def test_context_cli_no_state_file(mock_project):
    """Test that 'python3 -m governor context' outputs nothing when no state file exists."""
    env = os.environ.copy()
    state_dir = os.path.join(mock_project, ".ctx-state")
    os.makedirs(state_dir, exist_ok=True)

    project_hash = "context-test-nostate"
    env["CTX_STATE_DIR"] = state_dir
    env["CTX_PROJECT_HASH"] = project_hash

    # Create machine file but no state file
    with open(os.path.join(state_dir, f"{project_hash}.machine"), "w") as f:
        f.write("machines.tdd.TDD")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", "-m", "governor", "context"],
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == ""
