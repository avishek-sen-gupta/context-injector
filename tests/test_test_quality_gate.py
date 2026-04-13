# tests/test_test_quality_gate.py
import os
import tempfile
import pytest

from gates.base import GateContext, GateVerdict
from gates.test_quality import TestQualityGate


def _make_test_file(tmp_path, filename, content):
    """Write a Python test file and return its path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _make_context(tmp_path, files):
    """Build a GateContext with the given recent_files."""
    return GateContext(
        state_name="writing_tests",
        transition_name="pytest_fail",
        recent_tools=[f"Write({f})" for f in files],
        recent_files=files,
        machine=None,
        project_root=tmp_path,
    )


class TestHardViolations:
    def test_no_assertions_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    result = 1 + 1
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no_assertions" in i for i in result.issues)

    def test_assert_true_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    assert True
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("trivial_assertion" in i for i in result.issues)

    def test_assert_literal_number_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    assert 1
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_pytest_skip_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
import pytest
def test_something():
    pytest.skip("not ready")
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("skip_abuse" in i for i in result.issues)

    def test_pytest_xfail_decorator_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
import pytest
@pytest.mark.xfail
def test_something():
    assert 1 == 2
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("xfail_abuse" in i for i in result.issues)

    def test_valid_test_passes(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_addition():
    assert 1 + 1 == 2
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_no_test_files_passes(self, tmp_path):
        path = _make_test_file(tmp_path, "widget.py", """\
def compute():
    return 42
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_pytest_raises_counts_as_assertion(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
import pytest
def test_raises():
    with pytest.raises(ValueError):
        int("not a number")
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS
