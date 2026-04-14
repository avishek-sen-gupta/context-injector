# tests/test_gate_adapters.py
"""Tests for the thin gate adapters that wrap python-fp-lint."""

import os

import pytest

from gates.base import GateContext, GateVerdict
from gates.lint import LintGate
from gates.reassignment import ReassignmentGate


def _make_file(tmp_path, filename, content):
    path = os.path.join(str(tmp_path), filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _make_context(tmp_path, files):
    return GateContext(
        state_name="fixing_tests",
        transition_name="pytest_pass",
        recent_tools=[f"Write({f})" for f in files],
        recent_files=files,
        machine=None,
        project_root=str(tmp_path),
    )


class TestLintGateAdapter:
    """Verify LintGate adapter converts LintResult → GateResult."""

    def test_no_files_passes(self, tmp_path):
        ctx = _make_context(str(tmp_path), [])
        gate = LintGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_clean_file_passes(self, tmp_path):
        path = _make_file(tmp_path, "readme.md", "# Hello")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS


class TestReassignmentGateAdapter:
    """Verify ReassignmentGate adapter converts LintResult → GateResult."""

    def test_no_files_passes(self, tmp_path):
        ctx = _make_context(str(tmp_path), [])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_clean_file_passes(self, tmp_path):
        path = _make_file(tmp_path, "clean.py", "x = 1\ny = 2\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_reassignment_fails(self, tmp_path):
        path = _make_file(tmp_path, "dirty.py", "x = 1\nx = 2\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = ReassignmentGate()
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert len(result.issues) >= 1
