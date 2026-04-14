# tests/test_lint_cli.py
"""End-to-end smoke test for governor lint CLI via the python-fp-lint submodule.

Verifies that the submodule integration works: governor lint → thin adapters →
python-fp-lint LintGate/ReassignmentGate → rule detection.
"""

import os
import subprocess


def _run_lint(*args):
    return subprocess.run(
        ["python3", "-m", "governor", "lint", *args],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": "."},
    )


class TestSubmoduleIntegration:
    """Smoke tests: governor lint delegates to python-fp-lint via submodule."""

    def test_clean_file_passes(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n")
        result = _run_lint(str(f))
        assert result.returncode == 0
        assert "no violations" in result.stdout

    def test_semgrep_rule_detected(self, tmp_path):
        f = tmp_path / "dirty.py"
        f.write_text('d = {}\nd["key"] = "value"\n')
        result = _run_lint(str(f))
        assert result.returncode == 1
        assert "no-subscript-mutation" in result.stdout

    def test_reassignment_detected(self, tmp_path):
        f = tmp_path / "reassign.py"
        f.write_text("x = 1\nx = 2\n")
        result = _run_lint(str(f))
        assert result.returncode == 1
        assert "reassignment" in result.stdout.lower()
