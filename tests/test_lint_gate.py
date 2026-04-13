# tests/test_lint_gate.py
"""Tests for the LintGate — ast-grep based lint checking on transition boundaries."""

import os
import shutil
import pytest

from gates.base import GateContext, GateVerdict
from gates.lint import LintGate


def _make_file(tmp_path, filename, content):
    """Write a Python file and return its path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _make_context(tmp_path, files, rules_dir=None):
    """Build a GateContext with the given recent_files."""
    return GateContext(
        state_name="fixing_tests",
        transition_name="pytest_pass",
        recent_tools=[f"Write({f})" for f in files],
        recent_files=files,
        machine=None,
        project_root=str(tmp_path),
    )


@pytest.fixture
def rules_dir(tmp_path):
    """Create a minimal rules directory with one rule."""
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "no-bare-except.yml").write_text(
        'id: no-bare-except\nlanguage: python\nrule:\n  pattern: |\n'
        '    try:\n      $$$BODY\n    except:\n      $$$HANDLER\n'
        'message: "Bare except"\nseverity: warning\n'
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


@pytest.fixture
def multi_rules_dir(tmp_path):
    """Create a rules directory with multiple rules."""
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "no-bare-except.yml").write_text(
        'id: no-bare-except\nlanguage: python\nrule:\n  pattern: |\n'
        '    try:\n      $$$BODY\n    except:\n      $$$HANDLER\n'
        'message: "Bare except"\nseverity: warning\n'
    )
    (rules / "no-print.yml").write_text(
        'id: no-print\nlanguage: python\nrule:\n  pattern: print($$$ARGS)\n'
        'message: "print() — use logging"\nseverity: warning\n'
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


needs_sg = pytest.mark.skipif(
    shutil.which("sg") is None and shutil.which("ast-grep") is None,
    reason="ast-grep (sg) not installed",
)


class TestResolveRulesDir:
    """Tests for rules directory resolution logic."""

    def test_explicit_rules_dir_takes_priority(self, tmp_path):
        gate = LintGate(rules_dir="/explicit/path")
        assert gate._resolve_rules_dir(str(tmp_path)) == "/explicit/path"

    def test_project_local_rules_found(self, tmp_path):
        lint_dir = tmp_path / "scripts" / "lint"
        lint_dir.mkdir(parents=True)
        (lint_dir / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        gate = LintGate()
        assert gate._resolve_rules_dir(str(tmp_path)) == str(lint_dir)

    def test_falls_back_to_plugin_dir(self, tmp_path, monkeypatch):
        """When project has no scripts/lint/, falls back to plugin directory."""
        plugin_lint = tmp_path / "plugin" / "scripts" / "lint"
        plugin_lint.mkdir(parents=True)
        (plugin_lint / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        # Patch expanduser so ~ resolves to our fake plugin parent
        fake_home = tmp_path / "plugin"
        fake_home.mkdir(exist_ok=True)
        # Build the expected path: ~/.claude/plugins/context-injector/scripts/lint
        claude_lint = fake_home / ".claude" / "plugins" / "context-injector" / "scripts" / "lint"
        claude_lint.mkdir(parents=True)
        (claude_lint / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(fake_home) if p == "~" else p)
        gate = LintGate()
        # project_root has no scripts/lint, so should fall back to plugin dir
        empty_project = tmp_path / "empty_project"
        empty_project.mkdir()
        result = gate._resolve_rules_dir(str(empty_project))
        assert result == str(claude_lint)

    def test_returns_none_when_no_rules_found(self, tmp_path, monkeypatch):
        """When neither project nor plugin has rules, returns None."""
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "nonexistent") if p == "~" else p)
        gate = LintGate()
        assert gate._resolve_rules_dir(str(tmp_path)) is None


class TestLintGateWithoutSg:
    """Tests that work without ast-grep installed."""

    def test_passes_when_no_python_files(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "README.md", "# Hello")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_passes_when_no_recent_files(self, tmp_path, rules_dir):
        ctx = _make_context(str(tmp_path), [])
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_passes_when_sg_not_found(self, tmp_path, rules_dir, monkeypatch):
        """If ast-grep is not installed, gate should pass (not block)."""
        path = _make_file(tmp_path, "widget.py", "try:\n    pass\nexcept:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        monkeypatch.setattr(shutil, "which", lambda _: None)
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_filters_to_python_files_only(self, tmp_path, rules_dir):
        py_path = _make_file(tmp_path, "widget.py", "x = 1\n")
        md_path = _make_file(tmp_path, "notes.md", "# Notes\n")
        sh_path = _make_file(tmp_path, "run.sh", "echo hi\n")
        ctx = _make_context(str(tmp_path), [py_path, md_path, sh_path])
        gate = LintGate(rules_dir=rules_dir)
        filtered = gate._filter_python_files(ctx.recent_files)
        assert filtered == [py_path]

    def test_skips_nonexistent_files(self, tmp_path, rules_dir):
        fake = os.path.join(str(tmp_path), "gone.py")
        ctx = _make_context(str(tmp_path), [fake])
        gate = LintGate(rules_dir=rules_dir)
        filtered = gate._filter_python_files(ctx.recent_files)
        assert filtered == []


@needs_sg
class TestLintGateWithSg:
    """Tests that require ast-grep installed."""

    def test_clean_file_passes(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "widget.py", "def compute():\n    return 42\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_bare_except_fails(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "try:\n    x = 1\nexcept:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-bare-except" in i for i in result.issues)

    def test_multiple_violations_reported(self, tmp_path, multi_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "try:\n    print('hi')\nexcept:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=multi_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert len(result.issues) >= 2

    def test_only_scans_touched_files(self, tmp_path, rules_dir):
        """Untouched files with violations should not cause failure."""
        dirty = _make_file(tmp_path, "dirty.py",
            "try:\n    x = 1\nexcept:\n    pass\n")
        clean = _make_file(tmp_path, "clean.py", "x = 1\n")
        # Only clean.py is in recent_files
        ctx = _make_context(str(tmp_path), [clean])
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_message_includes_violation_details(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "try:\n    x = 1\nexcept:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert "widget.py" in result.message
        assert "no-bare-except" in result.message

    def test_deduplicates_files(self, tmp_path, rules_dir):
        """Same file touched multiple times should only be scanned once."""
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        ctx = _make_context(str(tmp_path), [path, path, path])
        gate = LintGate(rules_dir=rules_dir)
        filtered = gate._filter_python_files(ctx.recent_files)
        assert len(filtered) == 1
