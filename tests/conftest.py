import json
import os
import tempfile

import pytest


@pytest.fixture
def tmp_state_dir():
    """Temporary directory for state files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def tmp_audit_dir():
    """Temporary directory for audit JSONL files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def tmp_context_dir():
    """Temporary .claude directory with sample context files."""
    with tempfile.TemporaryDirectory() as d:
        core_dir = os.path.join(d, "core")
        cond_dir = os.path.join(d, "conditional")
        os.makedirs(core_dir)
        os.makedirs(cond_dir)

        with open(os.path.join(core_dir, "project-context.md"), "w") as f:
            f.write("# Project Context\nThis is a test project.\n")

        with open(os.path.join(cond_dir, "testing-patterns.md"), "w") as f:
            f.write("# Testing Patterns\nAlways write tests first.\n")

        with open(os.path.join(cond_dir, "refactoring.md"), "w") as f:
            f.write("# Refactoring\nKeep changes small.\n")

        with open(os.path.join(cond_dir, "code-review.md"), "w") as f:
            f.write("# Code Review\nCheck for correctness.\n")

        with open(os.path.join(cond_dir, "design-principles.md"), "w") as f:
            f.write("# Design Principles\nSingle responsibility.\n")

        yield d


@pytest.fixture
def sample_pre_tool_use_event():
    """A sample PreToolUse event as the hook would receive it."""
    return {
        "event": "pre_tool_use",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/project/tests/test_auth.py",
        },
        "session_id": "test-session-001",
        "timestamp": "2026-04-12T12:00:00Z",
    }


@pytest.fixture
def sample_declare_phase_event():
    """A DeclarePhase event (Bash echo intercepted by hook)."""
    return {
        "event": "pre_tool_use",
        "tool_name": "Bash",
        "tool_input": {
            "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
        },
        "session_id": "test-session-001",
        "timestamp": "2026-04-12T12:01:00Z",
    }
