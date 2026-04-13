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
        "tool_name": "Read",
        "tool_input": {"file_path": "/project/README.md"},
        "session_id": "integration-test",
        "timestamp": "2026-04-12T12:00:00Z",
    }

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "integration"
    env["CTX_MACHINE"] = "machines.feature_development.FeatureDevelopment"

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
    assert response["current_state"] == "planning"
    assert response["action"] in ("allow", "remind", "challenge", "block")


def test_governor_declaration_transition(mock_project):
    """Test that a DeclarePhase event triggers a state transition (with precondition met)."""
    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "integration2"
    env["CTX_MACHINE"] = "machines.feature_development.FeatureDevelopment"

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

    # Satisfy precondition for begin_impl: Read(*) and Bash(*)
    run_event({
        "event": "pre_tool_use",
        "tool_name": "Read",
        "tool_input": {"file_path": "/project/README.md"},
        "session_id": "integration-test-2",
        "timestamp": "2026-04-12T11:58:00Z",
    })
    run_event({
        "event": "pre_tool_use",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "session_id": "integration-test-2",
        "timestamp": "2026-04-12T11:59:00Z",
    })

    # Declare implementing
    response = run_event({
        "event": "pre_tool_use",
        "tool_name": "Bash",
        "tool_input": {
            "command": """echo '{"declare_phase": "implementing", "reason": "plan complete"}'""",
        },
        "session_id": "integration-test-2",
        "timestamp": "2026-04-12T12:00:00Z",
    })

    assert response["current_state"] == "implementing"
    assert response["transition"] == "planning -> implementing"


def test_full_feature_cycle_sequence(mock_project):
    """Test a complete planning → implementing → reviewing → committing cycle through the governor CLI."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_dir = os.path.join(mock_project, ".ctx-state")
    audit_dir = os.path.join(mock_project, ".ctx-audit")

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = state_dir
    env["CTX_AUDIT_DIR"] = audit_dir
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "e2e"
    env["CTX_MACHINE"] = "machines.feature_development.FeatureDevelopment"

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

    # 1. Start in planning — read a file (satisfies Read(*) precondition)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Read",
        "tool_input": {"file_path": "/p/README.md"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:00:00Z",
    })
    assert r["current_state"] == "planning"
    assert r["action"] == "allow"

    # 1b. Run a bash command (satisfies Bash(*) precondition)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:00:30Z",
    })
    assert r["current_state"] == "planning"

    # 2. Declare implementing
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "implementing", "reason": "plan ready"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:01:00Z",
    })
    assert r["current_state"] == "implementing"
    assert r["transition"] == "planning -> implementing"

    # 3. Edit a file (satisfies Edit(*) precondition for impl_complete)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Edit",
        "tool_input": {"file_path": "/p/src/auth.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:02:00Z",
    })
    assert r["current_state"] == "implementing"

    # 4. Declare reviewing
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "reviewing", "reason": "impl done"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:03:00Z",
    })
    assert r["current_state"] == "reviewing"

    # 5. Read and run tests (satisfies preconditions for review_passed)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Read",
        "tool_input": {"file_path": "/p/src/auth.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:03:30Z",
    })
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/ -v"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:03:45Z",
    })

    # 6. Declare committing
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "committing", "reason": "review passed"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:04:00Z",
    })
    assert r["current_state"] == "committing"

    # 7. Verify audit trail
    audit_file = os.path.join(audit_dir, "e2e.audit.json")
    assert os.path.exists(audit_file)
    from governor.audit import read_audit_log
    entries = read_audit_log(audit_file)
    assert len(entries) >= 7
    assert entries[0]["from_state"] == "planning"


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


class TestPortableHash:
    """Test that hooks/lib/hash.sh produces consistent MD5 hashes on any platform."""

    HASH_SH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hooks", "lib", "hash.sh",
    )

    def _run_hash(self, input_str):
        """Source hash.sh and call project_hash with the given input."""
        result = subprocess.run(
            ["sh", "-c", f'. "{self.HASH_SH}" && project_hash "$1"', "_", input_str],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"hash.sh failed: {result.stderr}"
        return result.stdout.strip()

    def test_deterministic(self):
        """Same input always produces the same hash."""
        h1 = self._run_hash("/tmp/test-project")
        h2 = self._run_hash("/tmp/test-project")
        assert h1 == h2

    def test_is_valid_md5(self):
        """Output is a 32-character lowercase hex string (standard MD5 digest)."""
        h = self._run_hash("/some/path")
        assert len(h) == 32, f"Expected 32 chars, got {len(h)}: {h!r}"
        assert all(c in "0123456789abcdef" for c in h), f"Non-hex chars in: {h!r}"

    def test_different_inputs_differ(self):
        """Different paths produce different hashes."""
        h1 = self._run_hash("/project/a")
        h2 = self._run_hash("/project/b")
        assert h1 != h2

    def test_known_value(self):
        """Verify against a known MD5 to catch algorithm mismatches across platforms."""
        # MD5 of the empty string is d41d8cd98f00b204e9800998ecf8427e
        h = self._run_hash("")
        assert h == "d41d8cd98f00b204e9800998ecf8427e"
