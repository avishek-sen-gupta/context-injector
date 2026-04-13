import os
import subprocess

import pytest


@pytest.fixture
def clean_file(tmp_path):
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n")
    return str(f)


@pytest.fixture
def dirty_file(tmp_path):
    f = tmp_path / "dirty.py"
    f.write_text('d = {}\nd["key"] = "value"\n')
    return str(f)


def _run_lint(*args):
    return subprocess.run(
        ["python3", "-m", "governor", "lint", *args],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": "."},
    )


class TestLintCLI:
    def test_clean_file_exits_zero(self, clean_file):
        result = _run_lint(clean_file)
        assert result.returncode == 0
        assert "no violations" in result.stdout

    def test_dirty_file_exits_nonzero(self, dirty_file):
        result = _run_lint(dirty_file)
        assert result.returncode == 1
        assert "violation" in result.stdout

    def test_glob_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text('d = {}\nd["k"] = 1\n')
        (tmp_path / "b.py").write_text("x = 1\n")
        result = _run_lint(str(tmp_path / "*.py"))
        assert result.returncode == 1
        assert "no-subscript-mutation" in result.stdout

    def test_no_args_exits_with_usage(self):
        result = _run_lint()
        assert result.returncode == 1
        assert "Usage" in result.stderr

    def test_no_matching_files_exits_with_message(self):
        result = _run_lint("/nonexistent/path/*.py")
        assert result.returncode == 1
        assert "No files matched" in result.stderr

    def test_setitem_detected(self, tmp_path):
        f = tmp_path / "setitem.py"
        f.write_text('d = {}\nd.__setitem__("k", 1)\n')
        result = _run_lint(str(f))
        assert result.returncode == 1
        assert "no-setitem-call" in result.stdout
