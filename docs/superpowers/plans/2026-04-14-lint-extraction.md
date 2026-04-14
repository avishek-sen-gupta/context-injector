# Lint Rules Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Semgrep + ast-grep lint rules, LintGate, and ReassignmentGate into a standalone repo (`python-fp-lint`) that can be used independently or consumed by context-injector as a git submodule.

**Architecture:** Create `~/code/python-fp-lint` as an independent Python package with its own result types (`LintResult`, `LintViolation`). The package contains `LintGate`, `ReassignmentGate`, rule files, and tests. In context-injector, `scripts/lint/` becomes a git submodule pointing at this repo, and the existing gate files become thin adapters that convert `LintResult` → `GateResult`.

**Tech Stack:** Python 3.10+, pytest, Semgrep, ast-grep, git submodules

**Two-repo plan:** Tasks 1–8 build the new `python-fp-lint` repo. Tasks 9–12 modify context-injector to consume it as a submodule.

---

### Task 1: Create python-fp-lint Repo and Package Structure

**Files:**
- Create: `~/code/python-fp-lint/pyproject.toml`
- Create: `~/code/python-fp-lint/python_fp_lint/__init__.py`

- [ ] **Step 1: Initialize the repo**

```bash
mkdir -p ~/code/python-fp-lint/python_fp_lint
mkdir -p ~/code/python-fp-lint/tests
cd ~/code/python-fp-lint
git init
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "python-fp-lint"
version = "0.1.0"
description = "Functional-programming lint rules for Python — Semgrep + ast-grep + beniget"
requires-python = ">=3.10"
dependencies = [
    "beniget>=0.5.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create __init__.py with public exports**

```python
"""python-fp-lint — functional-programming lint rules for Python."""

from python_fp_lint.result import LintResult, LintViolation
from python_fp_lint.lint_gate import LintGate
from python_fp_lint.reassignment_gate import ReassignmentGate

__all__ = ["LintGate", "ReassignmentGate", "LintResult", "LintViolation"]
```

Note: This will fail to import until Tasks 2–4 create the referenced modules. That's expected.

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
venv/
dist/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 5: Commit**

```bash
cd ~/code/python-fp-lint
git add pyproject.toml python_fp_lint/__init__.py .gitignore
git commit -m "feat: initialize python-fp-lint package structure"
```

---

### Task 2: Define LintResult and LintViolation Types

**Files:**
- Create: `~/code/python-fp-lint/python_fp_lint/result.py`
- Create: `~/code/python-fp-lint/tests/test_result.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_result.py
"""Tests for LintResult and LintViolation types."""

from python_fp_lint.result import LintResult, LintViolation


class TestLintViolation:
    def test_fields(self):
        v = LintViolation(rule="no-print", file="app.py", line=10, message="print() found")
        assert v.rule == "no-print"
        assert v.file == "app.py"
        assert v.line == 10
        assert v.message == "print() found"


class TestLintResult:
    def test_passing_result(self):
        r = LintResult(passed=True, violations=[])
        assert r.passed is True
        assert r.violations == []

    def test_failing_result(self):
        v = LintViolation(rule="no-print", file="app.py", line=10, message="print() found")
        r = LintResult(passed=False, violations=[v])
        assert r.passed is False
        assert len(r.violations) == 1
        assert r.violations[0].rule == "no-print"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/test_result.py -v
```

Expected: FAIL — `result.py` does not exist yet.

- [ ] **Step 3: Write the implementation**

```python
# python_fp_lint/result.py
"""Result types for python-fp-lint."""

from dataclasses import dataclass


@dataclass
class LintViolation:
    rule: str
    file: str
    line: int
    message: str


@dataclass
class LintResult:
    passed: bool
    violations: list[LintViolation]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/test_result.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/code/python-fp-lint
git add python_fp_lint/result.py tests/test_result.py
git commit -m "feat: add LintResult and LintViolation dataclasses"
```

---

### Task 3: Move and Refactor LintGate

**Files:**
- Create: `~/code/python-fp-lint/python_fp_lint/lint_gate.py`
- Reference: `context-injector/gates/lint.py` (source to move from)

The LintGate class moves from `gates/lint.py` with these changes:
- No longer inherits from `Gate` (from `gates.base`)
- `evaluate(changed_files: list[str], project_root: str) -> LintResult` instead of `evaluate(ctx: GateContext) -> GateResult`
- Rule discovery uses `__file__`-relative paths as primary, then `project_root/scripts/lint/`, then config.json fallback
- Returns `LintResult` with `LintViolation` objects instead of `GateResult` with `GateVerdict`

- [ ] **Step 1: Write the failing test**

Create a minimal test that verifies the new API:

```python
# tests/test_lint_gate.py
"""Tests for LintGate — dual-backend lint checking."""

import os
import shutil
import pytest

from python_fp_lint.lint_gate import LintGate
from python_fp_lint.result import LintResult


def _make_file(tmp_path, filename, content):
    """Write a Python file and return its path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


@pytest.fixture
def rules_dir(tmp_path):
    """Create a minimal rules directory with one Semgrep rule."""
    semgrep_rules = tmp_path / "semgrep-rules.yml"
    semgrep_rules.write_text(
        "rules:\n"
        "  - id: no-bare-except\n"
        "    pattern: |\n"
        "      try:\n"
        "          ...\n"
        "      except:\n"
        "          ...\n"
        '    message: "Bare except"\n'
        "    severity: WARNING\n"
        "    languages: [python]\n"
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    rules = tmp_path / "rules"
    rules.mkdir()
    return str(tmp_path)


needs_semgrep = pytest.mark.skipif(
    shutil.which("semgrep") is None,
    reason="semgrep not installed",
)

needs_sg = pytest.mark.skipif(
    shutil.which("sg") is None and shutil.which("ast-grep") is None,
    reason="ast-grep (sg) not installed",
)


class TestLintGateAPI:
    """Verify the new standalone API returns LintResult."""

    def test_returns_lint_result(self, tmp_path, rules_dir, monkeypatch):
        """evaluate() returns a LintResult, not a GateResult."""
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([path], str(tmp_path))
        assert isinstance(result, LintResult)

    def test_no_python_files_passes(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "README.md", "# Hello")
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True
        assert result.violations == []

    def test_empty_files_passes(self, tmp_path, rules_dir):
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([], str(tmp_path))
        assert result.passed is True

    def test_fails_when_semgrep_missing(self, tmp_path, rules_dir, monkeypatch):
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is False
        assert any("semgrep" in v.message.lower() for v in result.violations)


@needs_semgrep
class TestLintGateWithSemgrep:
    """Tests that require Semgrep installed."""

    def test_clean_file_passes(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "widget.py", "def compute():\n    return 42\n")
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

    def test_bare_except_fails(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "try:\n    x = 1\nexcept:\n    pass\n")
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is False
        assert any(v.rule == "no-bare-except" for v in result.violations)

    def test_violations_have_correct_fields(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "try:\n    x = 1\nexcept:\n    pass\n")
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([path], str(tmp_path))
        v = result.violations[0]
        assert v.rule == "no-bare-except"
        assert "widget.py" in v.file
        assert v.line > 0
        assert v.message != ""

    def test_deduplicates_files(self, tmp_path, rules_dir):
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate([path, path, path], str(tmp_path))
        assert result.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/test_lint_gate.py -v
```

Expected: FAIL — `lint_gate.py` does not exist yet.

- [ ] **Step 3: Write the implementation**

```python
# python_fp_lint/lint_gate.py
"""LintGate — dual-backend lint checking.

Runs Semgrep for the majority of lint rules, then ast-grep for the
rules that require tree-sitter-specific features (stopBy, has+kind).
Results are merged into a single violation list.
"""

import json
import os
import shutil
import subprocess

from python_fp_lint.result import LintResult, LintViolation


class LintGate:
    """Lint checker that runs Semgrep and ast-grep rules on Python files."""

    def __init__(self, rules_dir: str | None = None):
        self.rules_dir = rules_dir

    def evaluate(self, changed_files: list[str], project_root: str) -> LintResult:
        py_files = self._filter_python_files(changed_files)
        if not py_files:
            return LintResult(passed=True, violations=[])

        rules_dir = self._resolve_rules_dir(project_root)
        if rules_dir is None:
            return LintResult(passed=True, violations=[])

        # Semgrep is required
        semgrep = self._find_semgrep()
        if semgrep is None:
            return LintResult(
                passed=False,
                violations=[
                    LintViolation(
                        rule="tool-missing",
                        file="",
                        line=0,
                        message="semgrep binary not found. Install with: pip install semgrep",
                    )
                ],
            )

        violations = []

        # Run Semgrep (26 rules)
        semgrep_rules = os.path.join(rules_dir, "semgrep-rules.yml")
        if os.path.exists(semgrep_rules):
            violations.extend(self._run_semgrep(semgrep, semgrep_rules, py_files))

        # Run ast-grep (2 remaining rules) — optional
        sg = self._find_sg()
        sgconfig = os.path.join(rules_dir, "sgconfig.yml")
        if sg is not None and os.path.exists(sgconfig):
            violations.extend(self._run_sg(sg, rules_dir, py_files))

        return LintResult(passed=len(violations) == 0, violations=violations)

    @staticmethod
    def _filter_python_files(files: list[str]) -> list[str]:
        """Filter to existing, unique .py files."""
        seen = set()
        result = []
        for f in files:
            if f in seen:
                continue
            seen.add(f)
            if f.endswith(".py") and os.path.exists(f):
                result.append(f)
        return result

    @staticmethod
    def _find_semgrep() -> str | None:
        return shutil.which("semgrep")

    @staticmethod
    def _find_sg() -> str | None:
        return shutil.which("sg") or shutil.which("ast-grep")

    def _resolve_rules_dir(self, project_root: str) -> str | None:
        """Find the lint rules directory.

        Searches in order: explicit rules_dir, package-local (next to this file),
        project-local scripts/lint/, then lint_rules_dir from config.json.
        """
        if self.rules_dir:
            return self.rules_dir
        # Package-local: rule files live alongside this module
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            pkg_dir,
            os.path.join(project_root, "scripts", "lint"),
        ]
        config_dir = self._read_config_rules_dir()
        if config_dir:
            candidates.append(config_dir)
        for candidate in candidates:
            if os.path.isdir(candidate) and (
                os.path.exists(os.path.join(candidate, "sgconfig.yml"))
                or os.path.exists(os.path.join(candidate, "semgrep-rules.yml"))
            ):
                return candidate
        return None

    @staticmethod
    def _read_config_rules_dir() -> str | None:
        """Read lint_rules_dir from the plugin config.json."""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json",
        )
        if not os.path.exists(config_path):
            return None
        try:
            with open(config_path) as f:
                return json.load(f).get("lint_rules_dir")
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _run_semgrep(semgrep_path: str, rules_file: str, files: list[str]) -> list[LintViolation]:
        try:
            result = subprocess.run(
                [semgrep_path, "scan", "--config", rules_file, "--json", "--no-git-ignore"] + files,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []

        if not result.stdout.strip():
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        violations = []
        for entry in data.get("results", []):
            violations.append(LintViolation(
                rule=entry.get("check_id", "unknown").rsplit(".", 1)[-1],
                file=entry.get("path", ""),
                line=entry.get("start", {}).get("line", 0),
                message=entry.get("extra", {}).get("message", ""),
            ))
        return violations

    @staticmethod
    def _run_sg(sg_path: str, rules_dir: str, files: list[str]) -> list[LintViolation]:
        try:
            result = subprocess.run(
                [sg_path, "scan", "--json", "--config", os.path.join(rules_dir, "sgconfig.yml")] + files,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=rules_dir,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []

        if not result.stdout.strip():
            return []

        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError:
            entries = []
            for line in result.stdout.strip().splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        violations = []
        for entry in entries:
            violations.append(LintViolation(
                rule=entry.get("ruleId", "unknown"),
                file=entry.get("file", ""),
                line=entry.get("range", {}).get("start", {}).get("line", 0) + 1,
                message=entry.get("message", ""),
            ))
        return violations
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/test_lint_gate.py -v
```

Expected: All tests pass (some skipped if semgrep not installed).

- [ ] **Step 5: Commit**

```bash
cd ~/code/python-fp-lint
git add python_fp_lint/lint_gate.py tests/test_lint_gate.py
git commit -m "feat: add LintGate with dual Semgrep + ast-grep backend"
```

---

### Task 4: Move and Refactor ReassignmentGate

**Files:**
- Create: `~/code/python-fp-lint/python_fp_lint/reassignment_gate.py`
- Create: `~/code/python-fp-lint/tests/test_reassignment_gate.py`
- Reference: `context-injector/gates/reassignment.py` (source to move from)

Same changes as LintGate: no `Gate` base class, `evaluate(changed_files, project_root) -> LintResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reassignment_gate.py
"""Tests for the ReassignmentGate — beniget-based reassignment detection."""

import os
import pytest

from python_fp_lint.reassignment_gate import ReassignmentGate
from python_fp_lint.result import LintResult


def _make_file(tmp_path, filename, content):
    """Write a Python file and return its path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


class TestReassignmentGateCleanCode:
    """Code that should PASS — no reassignment."""

    def test_returns_lint_result(self, tmp_path):
        path = _make_file(str(tmp_path), "clean.py", "x = 1\n")
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert isinstance(result, LintResult)

    def test_single_assignment_passes(self, tmp_path):
        path = _make_file(str(tmp_path), "clean.py", "x = 1\ny = 2\n")
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

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
        path = _make_file(str(tmp_path), "clean.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

    def test_no_python_files_passes(self, tmp_path):
        path = _make_file(str(tmp_path), "readme.md", "# Hello\n")
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

    def test_empty_file_passes(self, tmp_path):
        path = _make_file(str(tmp_path), "empty.py", "")
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

    def test_function_params_not_flagged_as_dups(self, tmp_path):
        code = "def foo(x, y):\n    return x + y\n"
        path = _make_file(str(tmp_path), "clean.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

    def test_for_loop_target_not_flagged(self, tmp_path):
        code = "result = [i * 2 for i in range(10)]\n"
        path = _make_file(str(tmp_path), "clean.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

    def test_unpacking_not_flagged(self, tmp_path):
        code = "a, b, c = 1, 2, 3\n"
        path = _make_file(str(tmp_path), "clean.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True


class TestReassignmentGateDetection:
    """Code that should FAIL — contains reassignment."""

    def test_variable_reassignment_in_function(self, tmp_path):
        code = (
            "def foo():\n"
            "    x = 1\n"
            "    x = 2\n"
            "    return x\n"
        )
        path = _make_file(str(tmp_path), "dirty.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is False
        assert any(v.rule == "reassignment" for v in result.violations)

    def test_parameter_reassignment(self, tmp_path):
        code = (
            "def foo(x):\n"
            "    x = x + 1\n"
            "    return x\n"
        )
        path = _make_file(str(tmp_path), "dirty.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is False

    def test_module_level_reassignment(self, tmp_path):
        code = "x = 1\nx = 2\n"
        path = _make_file(str(tmp_path), "dirty.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is False

    def test_multiple_reassignments_reported(self, tmp_path):
        code = (
            "def foo():\n"
            "    a = 1\n"
            "    b = 2\n"
            "    a = 3\n"
            "    b = 4\n"
            "    return a + b\n"
        )
        path = _make_file(str(tmp_path), "dirty.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is False
        assert len(result.violations) >= 2

    def test_violation_has_correct_fields(self, tmp_path):
        code = "def foo():\n    x = 1\n    x = 2\n    return x\n"
        path = _make_file(str(tmp_path), "dirty.py", code)
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        v = result.violations[0]
        assert v.rule == "reassignment"
        assert "dirty.py" in v.file
        assert v.line > 0
        assert "x" in v.message

    def test_only_scans_provided_files(self, tmp_path):
        _make_file(str(tmp_path), "dirty.py", "x = 1\nx = 2\n")
        clean = _make_file(str(tmp_path), "clean.py", "y = 1\n")
        gate = ReassignmentGate()
        result = gate.evaluate([clean], str(tmp_path))
        assert result.passed is True

    def test_syntax_error_file_passes(self, tmp_path):
        path = _make_file(str(tmp_path), "broken.py", "def foo(\n")
        gate = ReassignmentGate()
        result = gate.evaluate([path], str(tmp_path))
        assert result.passed is True

    def test_nonexistent_file_passes(self, tmp_path):
        gate = ReassignmentGate()
        result = gate.evaluate(["/nonexistent/file.py"], str(tmp_path))
        assert result.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/test_reassignment_gate.py -v
```

Expected: FAIL — `reassignment_gate.py` does not exist yet.

- [ ] **Step 3: Write the implementation**

```python
# python_fp_lint/reassignment_gate.py
"""ReassignmentGate — beniget-based reassignment detection.

Uses def-use chain analysis to detect variables, parameters, or names
that are assigned more than once within the same scope.
"""

import ast
import os
from collections import defaultdict

import beniget

from python_fp_lint.result import LintResult, LintViolation


class ReassignmentGate:
    """Detects variable/parameter reassignment in Python files."""

    def evaluate(self, changed_files: list[str], project_root: str) -> LintResult:
        py_files = [
            f for f in dict.fromkeys(changed_files)
            if f.endswith(".py") and os.path.exists(f)
        ]
        if not py_files:
            return LintResult(passed=True, violations=[])

        all_violations = []
        for filepath in py_files:
            all_violations.extend(self._check_file(filepath))

        return LintResult(passed=len(all_violations) == 0, violations=all_violations)

    @staticmethod
    def _check_file(filepath: str) -> list[LintViolation]:
        try:
            with open(filepath) as f:
                source = f.read()
            tree = ast.parse(source, filename=filepath)
        except (SyntaxError, OSError):
            return []

        duc = beniget.DefUseChains()
        try:
            duc.visit(tree)
        except Exception:
            return []

        violations = []
        for scope_node, local_defs in duc.locals.items():
            names: dict[str, list] = defaultdict(list)
            for chain in local_defs:
                node = chain.node
                name = chain.name()
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(node, (ast.Import, ast.ImportFrom, ast.alias)):
                    continue
                names[name].append(node)

            for name, nodes in names.items():
                if len(nodes) > 1:
                    for node in nodes[1:]:
                        lineno = getattr(node, "lineno", 0)
                        scope_desc = _scope_description(scope_node)
                        violations.append(LintViolation(
                            rule="reassignment",
                            file=filepath,
                            line=lineno,
                            message=f"'{name}' reassigned (scope: {scope_desc})",
                        ))

        return violations


def _scope_description(node: ast.AST) -> str:
    if isinstance(node, ast.Module):
        return "module"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"function {node.name}()"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    return type(node).__name__
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/test_reassignment_gate.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd ~/code/python-fp-lint
git add python_fp_lint/reassignment_gate.py tests/test_reassignment_gate.py
git commit -m "feat: add ReassignmentGate with beniget def-use chain analysis"
```

---

### Task 5: Copy Rule Files and patterns_report.py

**Files:**
- Copy: `context-injector/scripts/lint/semgrep-rules.yml` → `~/code/python-fp-lint/python_fp_lint/semgrep-rules.yml`
- Copy: `context-injector/scripts/lint/sgconfig.yml` → `~/code/python-fp-lint/python_fp_lint/sgconfig.yml`
- Copy: `context-injector/scripts/lint/rules/no-deep-nesting.yml` → `~/code/python-fp-lint/python_fp_lint/rules/no-deep-nesting.yml`
- Copy: `context-injector/scripts/lint/rules/no-loop-mutation.yml` → `~/code/python-fp-lint/python_fp_lint/rules/no-loop-mutation.yml`
- Copy: `context-injector/scripts/lint/patterns_report.py` → `~/code/python-fp-lint/python_fp_lint/patterns_report.py`

Rule files live inside the `python_fp_lint/` package directory so `_resolve_rules_dir()` can find them via `__file__`.

- [ ] **Step 1: Copy all rule files**

```bash
cd ~/code/python-fp-lint
mkdir -p python_fp_lint/rules
cp ~/code/context-injector/scripts/lint/semgrep-rules.yml python_fp_lint/
cp ~/code/context-injector/scripts/lint/sgconfig.yml python_fp_lint/
cp ~/code/context-injector/scripts/lint/rules/*.yml python_fp_lint/rules/
cp ~/code/context-injector/scripts/lint/patterns_report.py python_fp_lint/
```

- [ ] **Step 2: Verify package-local rule discovery works**

```bash
cd ~/code/python-fp-lint
python -c "
from python_fp_lint.lint_gate import LintGate
gate = LintGate()
d = gate._resolve_rules_dir('/nonexistent')
print(f'Rules dir: {d}')
assert d is not None, 'Should find package-local rules'
import os
assert os.path.exists(os.path.join(d, 'semgrep-rules.yml'))
print('OK: package-local rule discovery works')
"
```

- [ ] **Step 3: Commit**

```bash
cd ~/code/python-fp-lint
git add python_fp_lint/semgrep-rules.yml python_fp_lint/sgconfig.yml python_fp_lint/rules/ python_fp_lint/patterns_report.py
git commit -m "feat: add Semgrep rules, ast-grep rules, and patterns report"
```

---

### Task 6: Add CLI Entry Point

**Files:**
- Create: `~/code/python-fp-lint/python_fp_lint/__main__.py`

- [ ] **Step 1: Write the implementation**

```python
# python_fp_lint/__main__.py
"""CLI entry point: python -m python_fp_lint check [options] file1.py file2.py"""

import argparse
import sys

from python_fp_lint.lint_gate import LintGate
from python_fp_lint.reassignment_gate import ReassignmentGate


def main():
    parser = argparse.ArgumentParser(
        prog="python-fp-lint",
        description="Functional-programming lint rules for Python",
    )
    sub = parser.add_subparsers(dest="command")
    check = sub.add_parser("check", help="Run lint checks on files")
    check.add_argument("files", nargs="+", help="Python files to check")
    check.add_argument("--semgrep-only", action="store_true", help="Run only Semgrep/ast-grep rules")
    check.add_argument("--reassignment-only", action="store_true", help="Run only reassignment checks")

    args = parser.parse_args()
    if args.command != "check":
        parser.print_help()
        sys.exit(1)

    violations = []
    run_lint = not args.reassignment_only
    run_reassignment = not args.semgrep_only

    if run_lint:
        result = LintGate().evaluate(args.files, ".")
        violations.extend(result.violations)

    if run_reassignment:
        result = ReassignmentGate().evaluate(args.files, ".")
        violations.extend(result.violations)

    if not violations:
        print("No violations found.")
        sys.exit(0)

    for v in violations:
        loc = f"{v.file}:{v.line}" if v.line else v.file
        print(f"  [{v.rule}] {loc} — {v.message}")

    print(f"\n{len(violations)} violation(s) found.")
    sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI runs**

```bash
cd ~/code/python-fp-lint
python -m python_fp_lint check --help
```

Expected: Shows usage with `--semgrep-only` and `--reassignment-only` flags.

- [ ] **Step 3: Commit**

```bash
cd ~/code/python-fp-lint
git add python_fp_lint/__main__.py
git commit -m "feat: add CLI entry point for standalone usage"
```

---

### Task 7: Add Full Test Suite from context-injector

**Files:**
- Modify: `~/code/python-fp-lint/tests/test_lint_gate.py` (add remaining tests from context-injector)

The tests from `context-injector/tests/test_lint_gate.py` that test specific Semgrep rules (TestSemgrepMultilineAndComboRules, TestSemgrepComplexRules, TestSemgrepSimplePatternRules, TestDeepNestingRule, TestLoopMutationRule) should be ported to the new repo. These tests exercise the rule files themselves.

Key adaptation: all tests change from `gate.evaluate(ctx)` → `gate.evaluate([path], str(tmp_path))` and assertions change from `result.verdict == GateVerdict.FAIL` → `result.passed is False` and `result.issues` → `result.violations`.

- [ ] **Step 1: Port the fixture for real semgrep rules**

Add to `tests/test_lint_gate.py`:

```python
@pytest.fixture
def full_semgrep_rules(tmp_path):
    """Create a rules directory pointing to the real semgrep-rules.yml."""
    import shutil as _shutil
    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "python_fp_lint")
    _shutil.copy(os.path.join(pkg_dir, "semgrep-rules.yml"), tmp_path / "semgrep-rules.yml")
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    rules = tmp_path / "rules"
    rules.mkdir()
    return str(tmp_path)


@pytest.fixture
def nesting_rules_dir(tmp_path):
    """Create a rules directory with the no-deep-nesting rule."""
    rules = tmp_path / "rules"
    rules.mkdir()
    import shutil as _shutil
    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "python_fp_lint")
    _shutil.copy(os.path.join(pkg_dir, "rules", "no-deep-nesting.yml"), rules / "no-deep-nesting.yml")
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


@pytest.fixture
def loop_mutation_rules_dir(tmp_path):
    """Create a rules directory with the no-loop-mutation rule."""
    rules = tmp_path / "rules"
    rules.mkdir()
    import shutil as _shutil
    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "python_fp_lint")
    _shutil.copy(os.path.join(pkg_dir, "rules", "no-loop-mutation.yml"), rules / "no-loop-mutation.yml")
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)
```

- [ ] **Step 2: Port Semgrep rule tests**

Port all test classes from context-injector's `test_lint_gate.py`, adapting the API:
- `_make_context()` calls → direct `[path]` lists
- `gate.evaluate(ctx)` → `gate.evaluate([path], str(tmp_path))`
- `result.verdict == GateVerdict.FAIL` → `result.passed is False`
- `result.verdict == GateVerdict.PASS` → `result.passed is True`
- `result.issues` checks like `any("no-bare-except" in i for i in result.issues)` → `any(v.rule == "no-bare-except" for v in result.violations)` (or `"no-bare-except" in v.rule`)

Port these test classes:
- `TestSemgrepMultilineAndComboRules` — all multiline/combo rule tests
- `TestSemgrepComplexRules` — pattern-not, pattern-inside rules
- `TestDeepNestingRule` — ast-grep nesting rule tests
- `TestLoopMutationRule` — ast-grep loop mutation tests

Also port `TestResolveRulesDir` with adaptations for the new package-local path.

The full test file after porting should be ~800 lines. Use the context-injector test file as the reference — adapt each test method mechanically.

- [ ] **Step 3: Run full test suite**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/ -v
```

Expected: All tests pass (some skipped if semgrep/ast-grep not installed).

- [ ] **Step 4: Commit**

```bash
cd ~/code/python-fp-lint
git add tests/
git commit -m "feat: add comprehensive test suite for lint and reassignment rules"
```

---

### Task 8: Push python-fp-lint to GitHub

**Files:** None (git operations only)

- [ ] **Step 1: Create remote and push**

```bash
cd ~/code/python-fp-lint
gh repo create avishek-sen-gupta/python-fp-lint --public --source=. --push
```

If the repo already exists:

```bash
cd ~/code/python-fp-lint
git remote add origin https://github.com/avishek-sen-gupta/python-fp-lint.git
git push -u origin main
```

---

### Task 9: Wire Submodule in context-injector

**Files:**
- Remove: `context-injector/scripts/lint/` (current contents)
- Add: git submodule at `scripts/lint/` pointing to `python-fp-lint`

- [ ] **Step 1: Remove current scripts/lint/ contents**

```bash
cd ~/code/context-injector
git rm -r scripts/lint/
```

- [ ] **Step 2: Add git submodule**

```bash
cd ~/code/context-injector
git submodule add https://github.com/avishek-sen-gupta/python-fp-lint.git scripts/lint
```

This creates `scripts/lint/` as a submodule and adds `.gitmodules`.

- [ ] **Step 3: Verify submodule contents**

```bash
ls scripts/lint/python_fp_lint/
ls scripts/lint/semgrep-rules.yml 2>/dev/null || ls scripts/lint/python_fp_lint/semgrep-rules.yml
```

Expected: The submodule contains the `python_fp_lint/` package, rule files, etc.

- [ ] **Step 4: Commit**

```bash
cd ~/code/context-injector
git add .gitmodules scripts/lint
git commit -m "feat: replace scripts/lint/ with python-fp-lint submodule"
```

---

### Task 10: Create Thin Gate Adapters in context-injector

**Files:**
- Modify: `context-injector/gates/lint.py` (replace with thin adapter)
- Modify: `context-injector/gates/reassignment.py` (replace with thin adapter)

- [ ] **Step 1: Write adapter test**

```python
# tests/test_gate_adapters.py
"""Tests for the thin gate adapters that wrap python-fp-lint."""

import os
import sys
import pytest

# Ensure the submodule is importable
_lint_pkg = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "lint")
if _lint_pkg not in sys.path:
    sys.path.insert(0, _lint_pkg)

from gates.base import GateContext, GateVerdict
from gates.lint import LintGate
from gates.reassignment import ReassignmentGate


def _make_file(tmp_path, filename, content):
    path = os.path.join(tmp_path, filename)
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/code/context-injector
python -m pytest tests/test_gate_adapters.py -v
```

Expected: FAIL — adapters not written yet.

- [ ] **Step 3: Add sys.path setup for submodule imports**

Add a `conftest.py` entry (or modify the existing one) to ensure the submodule is on `sys.path`:

Check if `conftest.py` exists at the project root. If so, add the sys.path line. If not, create it:

```python
# conftest.py (at project root, add this block if not present)
import os
import sys

# Make python-fp-lint submodule importable
_lint_pkg = os.path.join(os.path.dirname(__file__), "scripts", "lint")
if _lint_pkg not in sys.path:
    sys.path.insert(0, _lint_pkg)
```

- [ ] **Step 4: Replace gates/lint.py with thin adapter**

```python
# gates/lint.py
"""LintGate adapter — wraps python-fp-lint's LintGate for the governor gate protocol."""

import os
import sys

from gates.base import Gate, GateContext, GateResult, GateVerdict

# Ensure python-fp-lint submodule is importable
_lint_pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "lint")
if _lint_pkg not in sys.path:
    sys.path.insert(0, _lint_pkg)

from python_fp_lint import LintGate as _LintGate


class LintGate(Gate):
    """Gate adapter that delegates to python-fp-lint's LintGate."""

    name = "lint"

    def __init__(self, rules_dir: str | None = None):
        self._lint = _LintGate(rules_dir=rules_dir)

    def evaluate(self, ctx: GateContext) -> GateResult:
        result = self._lint.evaluate(ctx.recent_files, ctx.project_root)
        if result.passed:
            return GateResult(GateVerdict.PASS)
        return GateResult(
            GateVerdict.FAIL,
            message=self._format_violations(result.violations),
            issues=[f"{v.rule}:{v.file}:{v.line}" for v in result.violations],
        )

    @staticmethod
    def _format_violations(violations) -> str:
        lines = [f"GATE: lint — {len(violations)} violation(s) found:"]
        for v in violations:
            lines.append(f"  - [{v.rule}] {v.file}:{v.line} — {v.message}")
        lines.append("")
        lines.append("Fix these lint violations before the transition can proceed.")
        return "\n".join(lines)
```

- [ ] **Step 5: Replace gates/reassignment.py with thin adapter**

```python
# gates/reassignment.py
"""ReassignmentGate adapter — wraps python-fp-lint's ReassignmentGate for the governor gate protocol."""

import os
import sys

from gates.base import Gate, GateContext, GateResult, GateVerdict

# Ensure python-fp-lint submodule is importable
_lint_pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "lint")
if _lint_pkg not in sys.path:
    sys.path.insert(0, _lint_pkg)

from python_fp_lint import ReassignmentGate as _ReassignmentGate


class ReassignmentGate(Gate):
    """Gate adapter that delegates to python-fp-lint's ReassignmentGate."""

    name = "reassignment"

    def evaluate(self, ctx: GateContext) -> GateResult:
        result = _ReassignmentGate().evaluate(ctx.recent_files, ctx.project_root)
        if result.passed:
            return GateResult(GateVerdict.PASS)
        return GateResult(
            GateVerdict.FAIL,
            message=self._format_violations(result.violations),
            issues=[f"{v.rule}:{v.file}:{v.line}" for v in result.violations],
        )

    @staticmethod
    def _format_violations(violations) -> str:
        lines = [f"GATE: reassignment — {len(violations)} violation(s) found:"]
        for v in violations:
            lines.append(
                f"  - '{v.message}' at {v.file}:{v.line}"
            )
        lines.append("")
        lines.append("Use immutable patterns — avoid rebinding variables.")
        return "\n".join(lines)
```

- [ ] **Step 6: Run adapter tests**

```bash
cd ~/code/context-injector
python -m pytest tests/test_gate_adapters.py -v
```

Expected: All tests pass.

- [ ] **Step 7: Run full test suite**

```bash
cd ~/code/context-injector
python -m pytest tests/ -v
```

Expected: All existing tests still pass (the adapter preserves the old API).

- [ ] **Step 8: Commit**

```bash
cd ~/code/context-injector
git add conftest.py gates/lint.py gates/reassignment.py tests/test_gate_adapters.py
git commit -m "feat: replace lint/reassignment gates with thin adapters over python-fp-lint"
```

---

### Task 11: Update install-governor.sh and pyproject.toml

**Files:**
- Modify: `context-injector/install-governor.sh` (handle submodule + copy python_fp_lint package)
- Modify: `context-injector/pyproject.toml` (remove beniget from runtime deps)

- [ ] **Step 1: Update install-governor.sh lint installation section**

Replace lines 89–101 (the lint rules + config section) with:

```bash
# --- install lint rules (from python-fp-lint submodule) ---
echo "Installing lint rules..."
LINT_SRC="$PLUGIN_DIR/scripts/lint"
if [ ! -d "$LINT_SRC/python_fp_lint" ]; then
  echo "Initializing submodule..."
  cd "$PLUGIN_DIR" && git submodule update --init scripts/lint && cd -
fi

LINT_DIR="$HOME/.claude/plugins/context-injector/scripts/lint"
mkdir -p "$LINT_DIR/python_fp_lint/rules"
cp "$LINT_SRC/python_fp_lint/semgrep-rules.yml" "$LINT_DIR/python_fp_lint/"
cp "$LINT_SRC/python_fp_lint/sgconfig.yml" "$LINT_DIR/python_fp_lint/"
cp "$LINT_SRC/python_fp_lint/rules/"*.yml "$LINT_DIR/python_fp_lint/rules/"
cp "$LINT_SRC/python_fp_lint/"*.py "$LINT_DIR/python_fp_lint/"
# Also copy to legacy paths for config.json compatibility
cp "$LINT_SRC/python_fp_lint/semgrep-rules.yml" "$LINT_DIR/"
cp "$LINT_SRC/python_fp_lint/sgconfig.yml" "$LINT_DIR/"
mkdir -p "$LINT_DIR/rules"
cp "$LINT_SRC/python_fp_lint/rules/"*.yml "$LINT_DIR/rules/"

# --- write plugin config ---
echo "Writing plugin config..."
CONFIG_FILE="$HOME/.claude/plugins/context-injector/config.json"
LINT_RULES_PATH="$HOME/.claude/plugins/context-injector/scripts/lint/python_fp_lint"
printf '{"lint_rules_dir": "%s"}\n' "$LINT_RULES_PATH" > "$CONFIG_FILE"
```

- [ ] **Step 2: Remove beniget from context-injector's pyproject.toml**

In `pyproject.toml`, change:

```toml
dependencies = [
    "python-statemachine>=3.0.0",
    "tinydb>=4.0.0",
    "beniget>=0.5.0",
]
```

to:

```toml
dependencies = [
    "python-statemachine>=3.0.0",
    "tinydb>=4.0.0",
]
```

beniget is now a dependency of `python-fp-lint`, not context-injector directly. The submodule provides it at runtime.

- [ ] **Step 3: Regenerate uv.lock**

```bash
cd ~/code/context-injector
uv lock
```

- [ ] **Step 4: Commit**

```bash
cd ~/code/context-injector
git add install-governor.sh pyproject.toml uv.lock
git commit -m "chore: update installer for submodule layout, remove beniget from direct deps"
```

---

### Task 12: Remove Old Tests and Verify End-to-End

**Files:**
- Remove: `context-injector/tests/test_lint_gate.py` (moved to python-fp-lint)
- Remove: `context-injector/tests/test_reassignment_gate.py` (moved to python-fp-lint)

These test files tested the lint logic directly. That logic now lives in `python-fp-lint` with its own test suite. Context-injector keeps `test_gate_adapters.py` (adapter tests) and `test_governor_gates.py` (integration tests).

- [ ] **Step 1: Remove moved test files**

```bash
cd ~/code/context-injector
git rm tests/test_lint_gate.py tests/test_reassignment_gate.py
```

- [ ] **Step 2: Run full test suite**

```bash
cd ~/code/context-injector
uv run pytest tests/ -v
```

Expected: All remaining tests pass. The test count will be lower (lint/reassignment unit tests moved to the new repo), but all governor integration tests, adapter tests, and other tests pass.

- [ ] **Step 3: Verify install-governor.sh works**

```bash
cd ~/code/context-injector
bash install-governor.sh
```

Expected: Installs successfully, copies lint rules from submodule path.

- [ ] **Step 4: Verify python-fp-lint tests pass independently**

```bash
cd ~/code/python-fp-lint
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd ~/code/context-injector
git add -A
git commit -m "chore: remove migrated lint/reassignment tests (now in python-fp-lint)"
```

- [ ] **Step 6: Deploy changed files to plugin directory**

```bash
cp ~/code/context-injector/gates/lint.py ~/.claude/plugins/context-injector/gates/
cp ~/code/context-injector/gates/reassignment.py ~/.claude/plugins/context-injector/gates/
cp ~/code/context-injector/install-governor.sh ~/.claude/plugins/context-injector/
```
