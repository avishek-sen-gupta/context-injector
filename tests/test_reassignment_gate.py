# tests/test_reassignment_gate.py
"""Tests for the ReassignmentGate — beniget-based reassignment detection."""

import os
import pytest

from gates.base import GateContext, GateVerdict
from gates.reassignment import ReassignmentGate


def _make_file(tmp_path, filename, content):
    """Write a Python file and return its path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _make_context(tmp_path, files):
    """Build a GateContext with the given recent_files."""
    return GateContext(
        state_name="fixing_tests",
        transition_name="pytest_pass",
        recent_tools=[f"Write({f})" for f in files],
        recent_files=files,
        machine=None,
        project_root=str(tmp_path),
    )


class TestReassignmentGateCleanCode:
    """Code that should PASS — no reassignment."""

    def test_single_assignment_passes(self, tmp_path):
        path = _make_file(tmp_path, "clean.py", "x = 1\ny = 2\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_assignments_in_separate_scopes_pass(self, tmp_path):
        code = (
            "def foo():\n"
            "    x = 1\n"
            "    return x\n"
            "\n"
            "def bar():\n"
            "    x = 2\n"
            "    return x\n"
        )
        path = _make_file(tmp_path, "clean.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_no_python_files_passes(self, tmp_path):
        path = _make_file(tmp_path, "readme.md", "# Hello\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_empty_file_passes(self, tmp_path):
        path = _make_file(tmp_path, "empty.py", "")
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_function_params_not_flagged_as_dups(self, tmp_path):
        """A parameter used but never reassigned should pass."""
        code = "def foo(x, y):\n    return x + y\n"
        path = _make_file(tmp_path, "clean.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_for_loop_target_not_flagged(self, tmp_path):
        """for-loop variables are a single definition, not reassignment."""
        code = "result = [i * 2 for i in range(10)]\n"
        path = _make_file(tmp_path, "clean.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_unpacking_not_flagged(self, tmp_path):
        """Tuple unpacking is a single definition per name."""
        code = "a, b, c = 1, 2, 3\n"
        path = _make_file(tmp_path, "clean.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS


class TestReassignmentGateDetection:
    """Code that should FAIL — contains reassignment."""

    def test_variable_reassignment_in_function(self, tmp_path):
        code = (
            "def foo():\n"
            "    x = 1\n"
            "    x = 2\n"
            "    return x\n"
        )
        path = _make_file(tmp_path, "dirty.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("x" in issue for issue in result.issues)

    def test_parameter_reassignment(self, tmp_path):
        code = (
            "def foo(x):\n"
            "    x = x + 1\n"
            "    return x\n"
        )
        path = _make_file(tmp_path, "dirty.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("x" in issue for issue in result.issues)

    def test_module_level_reassignment(self, tmp_path):
        code = "x = 1\nx = 2\n"
        path = _make_file(tmp_path, "dirty.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("x" in issue for issue in result.issues)

    def test_multiple_reassignments_reported(self, tmp_path):
        code = (
            "def foo():\n"
            "    a = 1\n"
            "    b = 2\n"
            "    a = 3\n"
            "    b = 4\n"
            "    return a + b\n"
        )
        path = _make_file(tmp_path, "dirty.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert len(result.issues) >= 2

    def test_message_includes_file_and_line(self, tmp_path):
        code = "def foo():\n    x = 1\n    x = 2\n    return x\n"
        path = _make_file(tmp_path, "dirty.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert "dirty.py" in result.message
        assert "line" in result.message.lower() or ":" in result.message

    def test_only_scans_recent_files(self, tmp_path):
        """Untouched files should not be scanned."""
        dirty = _make_file(tmp_path, "dirty.py", "x = 1\nx = 2\n")
        clean = _make_file(tmp_path, "clean.py", "y = 1\n")
        ctx = _make_context(str(tmp_path), [clean])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_syntax_error_file_passes(self, tmp_path):
        """Files that fail to parse should not block."""
        path = _make_file(tmp_path, "broken.py", "def foo(\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_nonexistent_file_passes(self, tmp_path):
        ctx = _make_context(str(tmp_path), ["/nonexistent/file.py"])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS
