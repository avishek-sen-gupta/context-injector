# LintGate Semgrep Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate 25 ast-grep lint rules to Semgrep, add a new `no-optional-none` rule, update LintGate to dual-backend (Semgrep + ast-grep), and add comprehensive tests for all 28 rules.

**Architecture:** LintGate runs Semgrep for 26 rules, then ast-grep for the 2 rules requiring tree-sitter features. Semgrep is a hard dependency. Results are merged into a single violation list.

**Tech Stack:** Python 3.10+, Semgrep, ast-grep, pytest

**Spec:** `docs/superpowers/specs/2026-04-14-semgrep-migration-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/lint/semgrep-rules.yml` | Create | All 26 Semgrep rules |
| `scripts/lint/sgconfig.yml` | Keep | Points to `rules/` (2 ast-grep rules) |
| `scripts/lint/rules/no-deep-nesting.yml` | Keep | ast-grep rule |
| `scripts/lint/rules/no-loop-mutation.yml` | Keep | ast-grep rule |
| `scripts/lint/rules/` (25 other .yml files) | Delete | Migrated to Semgrep |
| `gates/lint.py` | Modify | Dual-backend LintGate |
| `install-governor.sh` | Modify | Add Semgrep dependency check, copy `semgrep-rules.yml` |
| `tests/test_lint_gate.py` | Modify | Comprehensive tests for all rules + dual-backend integration |

---

### Task 1: Create Semgrep Rules File

**Files:**
- Create: `scripts/lint/semgrep-rules.yml`

- [ ] **Step 1: Create the Semgrep rules file with all 26 rules**

```yaml
rules:
  # --- Simple pattern rules (16) ---

  - id: no-list-append
    pattern: $OBJ.append(...)
    message: "list.append() — use list concatenation or comprehension"
    severity: WARNING
    languages: [python]

  - id: no-list-extend
    pattern: $LIST.extend(...)
    message: "list.extend() — use list concatenation"
    severity: WARNING
    languages: [python]

  - id: no-list-insert
    pattern: $LIST.insert(...)
    message: "list.insert() — use list slicing + concatenation"
    severity: WARNING
    languages: [python]

  - id: no-list-pop
    pattern: $LIST.pop(...)
    message: "list.pop() — use list slicing"
    severity: WARNING
    languages: [python]

  - id: no-list-remove
    pattern: $LIST.remove(...)
    message: "list.remove() — use list comprehension filter"
    severity: WARNING
    languages: [python]

  - id: no-dict-clear
    pattern: $DICT.clear()
    message: "dict.clear() — reassign to empty dict instead"
    severity: WARNING
    languages: [python]

  - id: no-dict-update
    pattern: $DICT.update(...)
    message: "dict.update() — use {**d, **other} merge"
    severity: WARNING
    languages: [python]

  - id: no-dict-setdefault
    pattern: $DICT.setdefault(...)
    message: "dict.setdefault() — use explicit conditional or defaultdict at construction"
    severity: WARNING
    languages: [python]

  - id: no-set-add
    pattern: $SET.add(...)
    message: "set.add() — use set union"
    severity: WARNING
    languages: [python]

  - id: no-set-discard
    pattern: $SET.discard(...)
    message: "set.discard() — use set difference"
    severity: WARNING
    languages: [python]

  - id: no-subscript-mutation
    pattern: $OBJ[$KEY] = $VAL
    message: "Subscript mutation — use comprehensions or immutable update patterns"
    severity: WARNING
    languages: [python]

  - id: no-subscript-del
    pattern: del $OBJ[$KEY]
    message: "Subscript deletion — use comprehensions or immutable update patterns"
    severity: WARNING
    languages: [python]

  - id: no-is-none
    pattern: $X is None
    message: "is None check — use structural pattern matching or Option type"
    severity: WARNING
    languages: [python]

  - id: no-is-not-none
    pattern: $X is not None
    message: "is not None check — use structural pattern matching or Option type"
    severity: WARNING
    languages: [python]

  - id: no-print
    pattern: print(...)
    message: "print() — use logging instead"
    severity: WARNING
    languages: [python]

  - id: no-static-method
    pattern: "@staticmethod"
    message: "@staticmethod — use module-level functions instead"
    severity: WARNING
    languages: [python]

  # --- Multiline pattern rules (2) ---

  - id: no-bare-except
    pattern: |
      try:
          ...
      except:
          ...
    message: "Bare except: — catch specific exceptions"
    severity: WARNING
    languages: [python]

  - id: no-except-exception
    pattern: |
      try:
          ...
      except Exception:
          ...
    message: "except Exception: — catch specific exceptions"
    severity: WARNING
    languages: [python]

  # --- pattern-either rules (5) ---

  - id: no-relative-import
    patterns:
      - pattern-either:
          - pattern: "from . import $X"
          - pattern: "from .. import $X"
          - pattern: "from .$MOD import $X"
          - pattern: "from ..$MOD import $X"
    message: "Relative import — use absolute imports"
    severity: WARNING
    languages: [python]

  - id: no-setitem-call
    patterns:
      - pattern-either:
          - pattern: $OBJ.__setitem__($KEY, $VAL)
          - pattern: $TYPE.__setitem__($OBJ, $KEY, $VAL)
    message: "__setitem__() call — use comprehensions or immutable update patterns"
    severity: WARNING
    languages: [python]

  - id: no-subscript-augmented-mutation
    patterns:
      - pattern-either:
          - pattern: $OBJ[$KEY] += $VAL
          - pattern: $OBJ[$KEY] -= $VAL
          - pattern: $OBJ[$KEY] *= $VAL
          - pattern: $OBJ[$KEY] /= $VAL
          - pattern: $OBJ[$KEY] //= $VAL
          - pattern: $OBJ[$KEY] **= $VAL
          - pattern: $OBJ[$KEY] %= $VAL
          - pattern: $OBJ[$KEY] &= $VAL
          - pattern: $OBJ[$KEY] |= $VAL
          - pattern: $OBJ[$KEY] ^= $VAL
          - pattern: $OBJ[$KEY] >>= $VAL
          - pattern: $OBJ[$KEY] <<= $VAL
    message: "Subscript augmented mutation — use immutable update patterns"
    severity: WARNING
    languages: [python]

  - id: no-subscript-tuple-mutation
    patterns:
      - pattern-either:
          - pattern: $OBJ[$KEY], $...REST = $...VALS
          - pattern: $...REST, $OBJ[$KEY] = $...VALS
    message: "Tuple subscript mutation — use immutable update patterns"
    severity: WARNING
    languages: [python]

  - id: no-attribute-augmented-mutation
    patterns:
      - pattern-either:
          - pattern: $OBJ.$ATTR += $VAL
          - pattern: $OBJ.$ATTR -= $VAL
          - pattern: $OBJ.$ATTR *= $VAL
          - pattern: $OBJ.$ATTR /= $VAL
          - pattern: $OBJ.$ATTR //= $VAL
          - pattern: $OBJ.$ATTR **= $VAL
          - pattern: $OBJ.$ATTR %= $VAL
          - pattern: $OBJ.$ATTR &= $VAL
          - pattern: $OBJ.$ATTR |= $VAL
          - pattern: $OBJ.$ATTR ^= $VAL
          - pattern: $OBJ.$ATTR >>= $VAL
          - pattern: $OBJ.$ATTR <<= $VAL
    message: "Attribute augmented mutation — use immutable update patterns"
    severity: WARNING
    languages: [python]

  # --- pattern-either + pattern-not rule (1) ---

  - id: no-local-augmented-mutation
    patterns:
      - pattern-either:
          - pattern: $VAR += $VAL
          - pattern: $VAR -= $VAL
          - pattern: $VAR *= $VAL
          - pattern: $VAR /= $VAL
          - pattern: $VAR //= $VAL
          - pattern: $VAR **= $VAL
          - pattern: $VAR %= $VAL
          - pattern: $VAR &= $VAL
          - pattern: $VAR |= $VAL
          - pattern: $VAR ^= $VAL
          - pattern: $VAR >>= $VAL
          - pattern: $VAR <<= $VAL
      - pattern-not: $OBJ.$ATTR += $VAL
      - pattern-not: $OBJ.$ATTR -= $VAL
      - pattern-not: $OBJ.$ATTR *= $VAL
      - pattern-not: $OBJ.$ATTR /= $VAL
      - pattern-not: $OBJ.$ATTR //= $VAL
      - pattern-not: $OBJ.$ATTR **= $VAL
      - pattern-not: $OBJ.$ATTR %= $VAL
      - pattern-not: $OBJ.$ATTR &= $VAL
      - pattern-not: $OBJ.$ATTR |= $VAL
      - pattern-not: $OBJ.$ATTR ^= $VAL
      - pattern-not: $OBJ.$ATTR >>= $VAL
      - pattern-not: $OBJ.$ATTR <<= $VAL
      - pattern-not: $OBJ[$KEY] += $VAL
      - pattern-not: $OBJ[$KEY] -= $VAL
      - pattern-not: $OBJ[$KEY] *= $VAL
      - pattern-not: $OBJ[$KEY] /= $VAL
      - pattern-not: $OBJ[$KEY] //= $VAL
      - pattern-not: $OBJ[$KEY] **= $VAL
      - pattern-not: $OBJ[$KEY] %= $VAL
      - pattern-not: $OBJ[$KEY] &= $VAL
      - pattern-not: $OBJ[$KEY] |= $VAL
      - pattern-not: $OBJ[$KEY] ^= $VAL
      - pattern-not: $OBJ[$KEY] >>= $VAL
      - pattern-not: $OBJ[$KEY] <<= $VAL
    message: "Local augmented mutation — use immutable update patterns"
    severity: WARNING
    languages: [python]

  # --- pattern-inside rule (1) ---

  - id: no-none-default-param
    patterns:
      - pattern: $PARAM = None
      - pattern-inside: |
          def $F(...):
              ...
    message: "None default parameter — use empty structures or sentinel objects"
    severity: WARNING
    languages: [python]

  # --- New rule (1) ---

  - id: no-optional-none
    patterns:
      - pattern-either:
          - pattern: "Optional[$T]"
          - pattern: "$T | None"
          - pattern: "None | $T"
          - pattern: "Union[$T, None]"
          - pattern: "Union[None, $T]"
    message: "Avoid Optional/None unions — use sentinel values or separate code paths"
    severity: WARNING
    languages: [python]
```

- [ ] **Step 2: Verify Semgrep can parse the rules file**

Run: `semgrep scan --config scripts/lint/semgrep-rules.yml --dry-run scripts/lint/sgconfig.yml 2>&1 | head -5`
Expected: No parse errors. May show "no findings" which is fine.

- [ ] **Step 3: Commit**

```bash
git add scripts/lint/semgrep-rules.yml
git commit -m "feat: create Semgrep rules file with 26 lint rules"
```

---

### Task 2: Delete Migrated ast-grep Rules

**Files:**
- Delete: 25 `.yml` files from `scripts/lint/rules/` (all except `no-deep-nesting.yml` and `no-loop-mutation.yml`)

- [ ] **Step 1: Delete the 25 migrated ast-grep rule files**

```bash
cd scripts/lint/rules
rm no-list-append.yml no-list-extend.yml no-list-insert.yml no-list-pop.yml no-list-remove.yml
rm no-dict-clear.yml no-dict-update.yml no-dict-setdefault.yml
rm no-set-add.yml no-set-discard.yml
rm no-subscript-mutation.yml no-subscript-del.yml no-subscript-augmented-mutation.yml no-subscript-tuple-mutation.yml
rm no-attribute-augmented-mutation.yml no-local-augmented-mutation.yml
rm no-setitem-call.yml
rm no-is-none.yml no-is-not-none.yml
rm no-print.yml no-static-method.yml
rm no-bare-except.yml no-except-exception.yml
rm no-relative-import.yml no-none-default-param.yml
```

- [ ] **Step 2: Verify only 2 files remain**

Run: `ls scripts/lint/rules/`
Expected:
```
no-deep-nesting.yml
no-loop-mutation.yml
```

- [ ] **Step 3: Commit**

```bash
git add -u scripts/lint/rules/
git commit -m "refactor: delete 25 ast-grep rules migrated to Semgrep"
```

---

### Task 3: Update LintGate to Dual-Backend

**Files:**
- Modify: `gates/lint.py`
- Test: `tests/test_lint_gate.py`

- [ ] **Step 1: Write failing test for Semgrep binary requirement**

Add to `tests/test_lint_gate.py`:

```python
needs_semgrep = pytest.mark.skipif(
    shutil.which("semgrep") is None,
    reason="semgrep not installed",
)


class TestLintGateSemgrepRequired:
    """Tests for Semgrep as a hard dependency."""

    def test_fails_when_semgrep_missing(self, tmp_path, rules_dir, monkeypatch):
        """Gate should FAIL (not pass) when semgrep is missing."""
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        ctx = _make_context(str(tmp_path), [path])
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert "semgrep" in result.message.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_lint_gate.py::TestLintGateSemgrepRequired::test_fails_when_semgrep_missing -v`
Expected: FAIL (current LintGate doesn't check for Semgrep)

- [ ] **Step 3: Rewrite `gates/lint.py` with dual-backend support**

Replace the entire contents of `gates/lint.py` with:

```python
# gates/lint.py
"""LintGate — dual-backend lint checking at transition boundaries.

Runs Semgrep for the majority of lint rules, then ast-grep for the
rules that require tree-sitter-specific features (stopBy, has+kind).
Results are merged into a single violation list.
"""

import json
import os
import shutil
import subprocess

from gates.base import Gate, GateContext, GateResult, GateVerdict


class LintGate(Gate):
    """Gate that runs Semgrep and ast-grep lint rules on touched files."""

    name = "lint"

    def __init__(self, rules_dir: str | None = None):
        self.rules_dir = rules_dir

    def evaluate(self, ctx: GateContext) -> GateResult:
        py_files = self._filter_python_files(ctx.recent_files)
        if not py_files:
            return GateResult(GateVerdict.PASS)

        rules_dir = self._resolve_rules_dir(ctx.project_root)
        if rules_dir is None:
            return GateResult(GateVerdict.PASS)

        # Semgrep is required
        semgrep = self._find_semgrep()
        if semgrep is None:
            return GateResult(
                GateVerdict.FAIL,
                message="GATE: lint — semgrep binary not found. Install with: pip install semgrep",
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

        if not violations:
            return GateResult(GateVerdict.PASS)

        return GateResult(
            GateVerdict.FAIL,
            message=self._format_violations(violations),
            issues=[f"{v['ruleId']}:{v['file']}:{v['line']}" for v in violations],
        )

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
        """Find the semgrep binary."""
        return shutil.which("semgrep")

    @staticmethod
    def _find_sg() -> str | None:
        """Find the ast-grep binary."""
        return shutil.which("sg") or shutil.which("ast-grep")

    def _resolve_rules_dir(self, project_root: str) -> str | None:
        """Find the lint rules directory.

        Searches in order: explicit rules_dir, project-local scripts/lint/,
        then lint_rules_dir from the plugin config.json (written at install time).
        """
        if self.rules_dir:
            return self.rules_dir
        candidates = [
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
    def _run_semgrep(semgrep_path: str, rules_file: str, files: list[str]) -> list[dict]:
        """Run Semgrep scan on the given files and return parsed violations."""
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

        violations = []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        for entry in data.get("results", []):
            violations.append({
                "ruleId": entry.get("check_id", "unknown").rsplit(".", 1)[-1],
                "file": entry.get("path", ""),
                "line": entry.get("start", {}).get("line", 0),
                "message": entry.get("extra", {}).get("message", ""),
                "source": entry.get("extra", {}).get("lines", "").strip(),
            })

        return violations

    @staticmethod
    def _run_sg(sg_path: str, rules_dir: str, files: list[str]) -> list[dict]:
        """Run ast-grep scan on the given files and return parsed violations."""
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

        violations = []
        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError:
            entries = []
            for line in result.stdout.strip().splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        for entry in entries:
            violations.append({
                "ruleId": entry.get("ruleId", "unknown"),
                "file": entry.get("file", ""),
                "line": entry.get("range", {}).get("start", {}).get("line", 0) + 1,
                "message": entry.get("message", ""),
                "source": entry.get("lines", "").strip(),
            })

        return violations

    @staticmethod
    def _format_violations(violations: list[dict]) -> str:
        """Format violations into a blocking message."""
        lines = [f"GATE: lint — {len(violations)} violation(s) found:"]
        for v in violations:
            lines.append(f"  - [{v['ruleId']}] {v['file']}:{v['line']} — {v['message']}")
            if v["source"]:
                truncated = v["source"][:80] + ("..." if len(v["source"]) > 80 else "")
                lines.append(f"    {truncated}")
        lines.append("")
        lines.append("Fix these lint violations before the transition can proceed.")
        return "\n".join(lines)
```

- [ ] **Step 4: Run the failing test to verify it now passes**

Run: `python3 -m pytest tests/test_lint_gate.py::TestLintGateSemgrepRequired -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests to verify nothing broke**

Run: `python3 -m pytest tests/test_lint_gate.py -v`
Expected: All existing tests pass. The `TestLintGateWithSg` tests that use ast-grep-only fixtures may need fixture updates (handled in Task 4).

- [ ] **Step 6: Commit**

```bash
git add gates/lint.py tests/test_lint_gate.py
git commit -m "feat: update LintGate to dual-backend (Semgrep + ast-grep)"
```

---

### Task 4: Update Test Fixtures for Dual-Backend

**Files:**
- Modify: `tests/test_lint_gate.py`

The existing test fixtures create ast-grep rule files. Now that LintGate checks for Semgrep first, fixtures for Semgrep-migrated rules need to provide a `semgrep-rules.yml` instead.

- [ ] **Step 1: Replace `rules_dir` fixture**

Replace the existing `rules_dir` fixture with one that provides Semgrep rules:

```python
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
    # Keep sgconfig.yml so _resolve_rules_dir still works
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    rules = tmp_path / "rules"
    rules.mkdir()
    return str(tmp_path)
```

- [ ] **Step 2: Replace `multi_rules_dir` fixture**

```python
@pytest.fixture
def multi_rules_dir(tmp_path):
    """Create a rules directory with multiple Semgrep rules."""
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
        "  - id: no-print\n"
        "    pattern: print(...)\n"
        '    message: "print() — use logging"\n'
        "    severity: WARNING\n"
        "    languages: [python]\n"
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    rules = tmp_path / "rules"
    rules.mkdir()
    return str(tmp_path)
```

- [ ] **Step 3: Replace `mutation_rules_dir` fixture**

```python
@pytest.fixture
def mutation_rules_dir(tmp_path):
    """Create a rules directory with subscript mutation Semgrep rules."""
    semgrep_rules = tmp_path / "semgrep-rules.yml"
    semgrep_rules.write_text(
        "rules:\n"
        "  - id: no-subscript-mutation\n"
        "    pattern: $OBJ[$KEY] = $VAL\n"
        '    message: "Subscript mutation"\n'
        "    severity: WARNING\n"
        "    languages: [python]\n"
        "  - id: no-subscript-augmented-mutation\n"
        "    patterns:\n"
        "      - pattern-either:\n"
        "          - pattern: $OBJ[$KEY] += $VAL\n"
        "          - pattern: $OBJ[$KEY] -= $VAL\n"
        "          - pattern: $OBJ[$KEY] *= $VAL\n"
        '    message: "Subscript augmented mutation"\n'
        "    severity: WARNING\n"
        "    languages: [python]\n"
        "  - id: no-subscript-del\n"
        "    pattern: del $OBJ[$KEY]\n"
        '    message: "Subscript deletion"\n'
        "    severity: WARNING\n"
        "    languages: [python]\n"
        "  - id: no-subscript-tuple-mutation\n"
        "    patterns:\n"
        "      - pattern-either:\n"
        "          - pattern: $OBJ[$KEY], $...REST = $...VALS\n"
        "          - pattern: $...REST, $OBJ[$KEY] = $...VALS\n"
        '    message: "Tuple subscript mutation"\n'
        "    severity: WARNING\n"
        "    languages: [python]\n"
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    rules = tmp_path / "rules"
    rules.mkdir()
    return str(tmp_path)
```

- [ ] **Step 4: Update `needs_sg` skip marker and add `needs_semgrep`**

Replace:
```python
needs_sg = pytest.mark.skipif(
    shutil.which("sg") is None and shutil.which("ast-grep") is None,
    reason="ast-grep (sg) not installed",
)
```

With:
```python
needs_sg = pytest.mark.skipif(
    shutil.which("sg") is None and shutil.which("ast-grep") is None,
    reason="ast-grep (sg) not installed",
)

needs_semgrep = pytest.mark.skipif(
    shutil.which("semgrep") is None,
    reason="semgrep not installed",
)
```

- [ ] **Step 5: Change `TestLintGateWithSg` to use `needs_semgrep`**

The tests in `TestLintGateWithSg` now use Semgrep fixtures, so they need `@needs_semgrep` instead of `@needs_sg`:

```python
@needs_semgrep
class TestLintGateWithSemgrep:
    """Tests that require Semgrep installed."""

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
        dirty = _make_file(tmp_path, "dirty.py",
            "try:\n    x = 1\nexcept:\n    pass\n")
        clean = _make_file(tmp_path, "clean.py", "x = 1\n")
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
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        ctx = _make_context(str(tmp_path), [path, path, path])
        gate = LintGate(rules_dir=rules_dir)
        filtered = gate._filter_python_files(ctx.recent_files)
        assert len(filtered) == 1

    def test_augmented_subscript_mutation_fails(self, tmp_path, mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def increment(d, key, amount=1):\n    d[key] += amount\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-subscript-augmented-mutation" in i for i in result.issues)

    def test_subscript_del_fails(self, tmp_path, mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def remove(d, k):\n    del d[k]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-subscript-del" in i for i in result.issues)

    def test_tuple_subscript_mutation_fails(self, tmp_path, mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def swap(d, k1, k2):\n    d[k1], d[k2] = d[k2], d[k1]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-subscript-tuple-mutation" in i for i in result.issues)

    def test_all_dict_mutations_caught(self, tmp_path, mutation_rules_dir):
        code = (
            "def swap_values(d, key1, key2):\n"
            "    d[key1], d[key2] = d[key2], d[key1]\n"
            "\n"
            "def increment_value(d, key, amount=1):\n"
            "    d[key] += amount\n"
            "\n"
            "def filter_keys(d, keys):\n"
            "    for k in list(d):\n"
            "        if k not in keys:\n"
            "            del d[k]\n"
        )
        path = _make_file(tmp_path, "dict_transform.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert len(result.issues) >= 3
```

- [ ] **Step 6: Update `TestLintGateWithoutSg` for new behavior**

The test `test_passes_when_sg_not_found` needs updating — now when BOTH semgrep and sg are missing, it should FAIL (semgrep is required). Rename the class and update:

```python
class TestLintGateWithoutTools:
    """Tests that work without linting tools installed."""

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

    def test_fails_when_semgrep_not_found(self, tmp_path, rules_dir, monkeypatch):
        """If semgrep is not installed, gate should FAIL."""
        path = _make_file(tmp_path, "widget.py", "try:\n    pass\nexcept:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        monkeypatch.setattr(shutil, "which", lambda _: None)
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert "semgrep" in result.message.lower()

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
```

- [ ] **Step 7: Run all tests**

Run: `python3 -m pytest tests/test_lint_gate.py -v`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add tests/test_lint_gate.py
git commit -m "refactor: update test fixtures for Semgrep-based LintGate"
```

---

### Task 5: Comprehensive Semgrep Rule Tests — Simple Patterns

**Files:**
- Modify: `tests/test_lint_gate.py`

Add a `full_semgrep_rules` fixture that points to the actual project `semgrep-rules.yml`, then test each of the 16 simple pattern rules.

- [ ] **Step 1: Add the `full_semgrep_rules` fixture**

```python
@pytest.fixture
def full_semgrep_rules(tmp_path):
    """Create a rules directory pointing to the real semgrep-rules.yml."""
    import shutil as _shutil
    src = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "scripts", "lint", "semgrep-rules.yml")
    _shutil.copy(src, tmp_path / "semgrep-rules.yml")
    # Also need sgconfig.yml for _resolve_rules_dir
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    rules = tmp_path / "rules"
    rules.mkdir()
    return str(tmp_path)
```

- [ ] **Step 2: Add test class for simple pattern rules**

```python
@needs_semgrep
class TestSemgrepSimplePatternRules:
    """Comprehensive tests for simple-pattern Semgrep rules."""

    def test_no_list_append_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = []\nitems.append(1)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-list-append" in i for i in result.issues)

    def test_no_list_append_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [1, 2, 3]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-list-append" in i for i in (result.issues or []))

    def test_no_list_extend_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = []\nitems.extend([1, 2])\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-list-extend" in i for i in result.issues)

    def test_no_list_extend_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [1] + [2, 3]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-list-extend" in i for i in (result.issues or []))

    def test_no_list_insert_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [2, 3]\nitems.insert(0, 1)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-list-insert" in i for i in result.issues)

    def test_no_list_insert_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [1] + [2, 3]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-list-insert" in i for i in (result.issues or []))

    def test_no_list_pop_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [1, 2, 3]\nitems.pop(0)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-list-pop" in i for i in result.issues)

    def test_no_list_pop_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [1, 2, 3]\nfirst, rest = items[0], items[1:]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-list-pop" in i for i in (result.issues or []))

    def test_no_list_remove_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [1, 2, 3]\nitems.remove(2)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-list-remove" in i for i in result.issues)

    def test_no_list_remove_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "items = [x for x in [1, 2, 3] if x != 2]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-list-remove" in i for i in (result.issues or []))

    def test_no_dict_clear_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {1: 2}\nd.clear()\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-dict-clear" in i for i in result.issues)

    def test_no_dict_clear_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {}\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-dict-clear" in i for i in (result.issues or []))

    def test_no_dict_update_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {}\nd.update({1: 2})\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-dict-update" in i for i in result.issues)

    def test_no_dict_update_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {**a, **b}\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-dict-update" in i for i in (result.issues or []))

    def test_no_dict_setdefault_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {}\nd.setdefault('k', [])\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-dict-setdefault" in i for i in result.issues)

    def test_no_dict_setdefault_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from collections import defaultdict\nd = defaultdict(list)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-dict-setdefault" in i for i in (result.issues or []))

    def test_no_set_add_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "s = set()\ns.add(1)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-set-add" in i for i in result.issues)

    def test_no_set_add_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "s = {1} | {2}\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-set-add" in i for i in (result.issues or []))

    def test_no_set_discard_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "s = {1, 2}\ns.discard(1)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-set-discard" in i for i in result.issues)

    def test_no_set_discard_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "s = {1, 2} - {1}\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-set-discard" in i for i in (result.issues or []))

    def test_no_subscript_mutation_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {}\nd['key'] = 'val'\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-subscript-mutation" in i for i in result.issues)

    def test_no_subscript_mutation_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {'key': 'val'}\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-subscript-mutation" in i for i in (result.issues or []))

    def test_no_subscript_del_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {'a': 1}\ndel d['a']\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-subscript-del" in i for i in result.issues)

    def test_no_subscript_del_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {k: v for k, v in d.items() if k != 'a'}\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-subscript-del" in i for i in (result.issues or []))

    def test_no_is_none_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x):\n    if x is None:\n        return 0\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-is-none" in i for i in result.issues)

    def test_no_is_none_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x):\n    if x == 0:\n        return 0\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-is-none" in i for i in (result.issues or []))

    def test_no_is_not_none_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x):\n    if x is not None:\n        return x\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-is-not-none" in i for i in result.issues)

    def test_no_is_not_none_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x):\n    if x != 0:\n        return x\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-is-not-none" in i for i in (result.issues or []))

    def test_no_print_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "print('hello')\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-print" in i for i in result.issues)

    def test_no_print_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "import logging\nlogging.info('hello')\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-print" in i for i in (result.issues or []))

    def test_no_static_method_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "class Foo:\n    @staticmethod\n    def bar():\n        pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-static-method" in i for i in result.issues)

    def test_no_static_method_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "class Foo:\n    @classmethod\n    def bar(cls):\n        pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-static-method" in i for i in (result.issues or []))
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_lint_gate.py::TestSemgrepSimplePatternRules -v`
Expected: All 32 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_lint_gate.py
git commit -m "test: add comprehensive tests for 16 simple-pattern Semgrep rules"
```

---

### Task 6: Comprehensive Semgrep Rule Tests — Multiline and pattern-either Rules

**Files:**
- Modify: `tests/test_lint_gate.py`

- [ ] **Step 1: Add test class for multiline and pattern-either rules**

```python
@needs_semgrep
class TestSemgrepMultilineAndComboRules:
    """Tests for multiline patterns and pattern-either Semgrep rules."""

    # --- no-bare-except ---
    def test_no_bare_except_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "try:\n    x = 1\nexcept:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-bare-except" in i for i in result.issues)

    def test_no_bare_except_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "try:\n    x = 1\nexcept ValueError:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-bare-except" in i for i in (result.issues or []))

    # --- no-except-exception ---
    def test_no_except_exception_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "try:\n    x = 1\nexcept Exception:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-except-exception" in i for i in result.issues)

    def test_no_except_exception_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "try:\n    x = 1\nexcept ValueError:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-except-exception" in i for i in (result.issues or []))

    # --- no-relative-import ---
    def test_no_relative_import_dot_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from . import utils\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-relative-import" in i for i in result.issues)

    def test_no_relative_import_dotdot_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from ..models import User\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-relative-import" in i for i in result.issues)

    def test_no_relative_import_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from mypackage import utils\nimport os\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-relative-import" in i for i in (result.issues or []))

    # --- no-setitem-call ---
    def test_no_setitem_call_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {}\nd.__setitem__('k', 'v')\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-setitem-call" in i for i in result.issues)

    def test_no_setitem_call_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {'k': 'v'}\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-setitem-call" in i for i in (result.issues or []))

    # --- no-subscript-augmented-mutation ---
    def test_no_subscript_augmented_mutation_plus_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {'a': 1}\nd['a'] += 1\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-subscript-augmented-mutation" in i for i in result.issues)

    def test_no_subscript_augmented_mutation_shift_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {'a': 8}\nd['a'] >>= 2\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-subscript-augmented-mutation" in i for i in result.issues)

    def test_no_subscript_augmented_mutation_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "x = 1\nx += 1\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-subscript-augmented-mutation" in i for i in (result.issues or []))

    # --- no-subscript-tuple-mutation ---
    def test_no_subscript_tuple_mutation_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "d = {}\nd['a'], d['b'] = 1, 2\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-subscript-tuple-mutation" in i for i in result.issues)

    def test_no_subscript_tuple_mutation_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "a, b = 1, 2\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-subscript-tuple-mutation" in i for i in (result.issues or []))

    # --- no-attribute-augmented-mutation ---
    def test_no_attribute_augmented_mutation_plus_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "class C:\n    x = 0\nc = C()\nc.x += 1\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-attribute-augmented-mutation" in i for i in result.issues)

    def test_no_attribute_augmented_mutation_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "x = 1\nx += 1\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-attribute-augmented-mutation" in i for i in (result.issues or []))
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_lint_gate.py::TestSemgrepMultilineAndComboRules -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_lint_gate.py
git commit -m "test: add comprehensive tests for multiline and pattern-either Semgrep rules"
```

---

### Task 7: Comprehensive Semgrep Rule Tests — Complex Rules

**Files:**
- Modify: `tests/test_lint_gate.py`

Tests for `no-local-augmented-mutation`, `no-none-default-param`, and `no-optional-none`.

- [ ] **Step 1: Add test class for complex Semgrep rules**

```python
@needs_semgrep
class TestSemgrepComplexRules:
    """Tests for rules using pattern-not, pattern-inside, and the new no-optional-none rule."""

    # --- no-local-augmented-mutation ---
    def test_no_local_augmented_mutation_local_var_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "x = 1\nx += 1\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-local-augmented-mutation" in i for i in result.issues)

    def test_no_local_augmented_mutation_all_operators(self, tmp_path, full_semgrep_rules):
        """All 12 augmented assignment operators on local vars should be caught."""
        code = (
            "a = 1\na += 1\n"
            "b = 1\nb -= 1\n"
            "c = 1\nc *= 2\n"
            "d = 1\nd /= 2\n"
            "e = 1\ne //= 2\n"
            "f = 1\nf **= 2\n"
            "g = 10\ng %= 3\n"
            "h = 0xFF\nh &= 0x0F\n"
            "i = 0x0F\ni |= 0xF0\n"
            "j = 0xFF\nj ^= 0x0F\n"
            "k = 8\nk >>= 2\n"
            "l = 1\nl <<= 2\n"
        )
        path = _make_file(tmp_path, "widget.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        local_violations = [i for i in result.issues if "no-local-augmented-mutation" in i]
        assert len(local_violations) >= 12

    def test_no_local_augmented_mutation_attribute_pass(self, tmp_path, full_semgrep_rules):
        """obj.attr += val should NOT trigger no-local-augmented-mutation."""
        path = _make_file(tmp_path, "widget.py", "class C:\n    x = 0\nc = C()\nc.x += 1\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-local-augmented-mutation" in i for i in (result.issues or []))

    def test_no_local_augmented_mutation_subscript_pass(self, tmp_path, full_semgrep_rules):
        """obj[key] += val should NOT trigger no-local-augmented-mutation."""
        path = _make_file(tmp_path, "widget.py", "d = {'a': 1}\nd['a'] += 1\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-local-augmented-mutation" in i for i in (result.issues or []))

    # --- no-none-default-param ---
    def test_no_none_default_param_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x=None):\n    return x\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-none-default-param" in i for i in result.issues)

    def test_no_none_default_param_multiple_params_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x, y=None, z=None):\n    return x\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-none-default-param" in i for i in result.issues)

    def test_no_none_default_param_non_none_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x=0, y=''):\n    return x\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-none-default-param" in i for i in (result.issues or []))

    def test_no_none_default_param_assignment_outside_func_pass(self, tmp_path, full_semgrep_rules):
        """x = None outside function parameters should NOT trigger this rule."""
        path = _make_file(tmp_path, "widget.py", "x = None\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-none-default-param" in i for i in (result.issues or []))

    # --- no-optional-none ---
    def test_no_optional_none_optional_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from typing import Optional\ndef f(x: Optional[str]):\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-optional-none" in i for i in result.issues)

    def test_no_optional_none_pipe_none_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x: str | None):\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-optional-none" in i for i in result.issues)

    def test_no_optional_none_none_pipe_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x: None | str):\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-optional-none" in i for i in result.issues)

    def test_no_optional_none_union_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from typing import Union\ndef f(x: Union[str, None]):\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-optional-none" in i for i in result.issues)

    def test_no_optional_none_union_reversed_fail(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from typing import Union\ndef f(x: Union[None, str]):\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert any("no-optional-none" in i for i in result.issues)

    def test_no_optional_none_clean_type_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "def f(x: str):\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-optional-none" in i for i in (result.issues or []))

    def test_no_optional_none_union_without_none_pass(self, tmp_path, full_semgrep_rules):
        path = _make_file(tmp_path, "widget.py", "from typing import Union\ndef f(x: Union[str, int]):\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=full_semgrep_rules)
        result = gate.evaluate(ctx)
        assert not any("no-optional-none" in i for i in (result.issues or []))
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_lint_gate.py::TestSemgrepComplexRules -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_lint_gate.py
git commit -m "test: add comprehensive tests for complex Semgrep rules (pattern-not, pattern-inside, no-optional-none)"
```

---

### Task 8: Dual-Backend Integration Tests

**Files:**
- Modify: `tests/test_lint_gate.py`

- [ ] **Step 1: Add a fixture that has both Semgrep and ast-grep rules**

```python
@pytest.fixture
def dual_backend_rules_dir(tmp_path):
    """Create a rules directory with both Semgrep and ast-grep rules."""
    import shutil as _shutil
    # Copy Semgrep rules
    src_semgrep = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "scripts", "lint", "semgrep-rules.yml")
    _shutil.copy(src_semgrep, tmp_path / "semgrep-rules.yml")
    # Copy ast-grep rules
    rules = tmp_path / "rules"
    rules.mkdir()
    for rule in ["no-deep-nesting.yml", "no-loop-mutation.yml"]:
        src = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "scripts", "lint", "rules", rule)
        _shutil.copy(src, rules / rule)
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)
```

- [ ] **Step 2: Add dual-backend integration test class**

```python
@needs_semgrep
class TestLintGateDualBackend:
    """Integration tests for the dual-backend LintGate."""

    def test_no_violations_passes(self, tmp_path, dual_backend_rules_dir):
        path = _make_file(tmp_path, "widget.py", "def compute():\n    return 42\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=dual_backend_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    @needs_sg
    def test_both_backends_violations_merged(self, tmp_path, dual_backend_rules_dir):
        """File with Semgrep violation (.append) AND ast-grep violation (nested for)."""
        code = (
            "def f(matrix):\n"
            "    result = []\n"
            "    result.append(1)\n"
            "    for row in matrix:\n"
            "        for cell in row:\n"
            "            pass\n"
        )
        path = _make_file(tmp_path, "widget.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=dual_backend_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        rule_ids = " ".join(result.issues)
        assert "no-list-append" in rule_ids
        assert "no-deep-nesting" in rule_ids

    def test_semgrep_only_violation(self, tmp_path, dual_backend_rules_dir):
        path = _make_file(tmp_path, "widget.py", "items = []\nitems.append(1)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=dual_backend_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-list-append" in i for i in result.issues)

    @needs_sg
    def test_ast_grep_only_violation(self, tmp_path, dual_backend_rules_dir):
        code = (
            "def f(matrix):\n"
            "    for row in matrix:\n"
            "        for cell in row:\n"
            "            pass\n"
        )
        path = _make_file(tmp_path, "widget.py", code)
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=dual_backend_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-deep-nesting" in i for i in result.issues)

    def test_semgrep_missing_fails_gate(self, tmp_path, dual_backend_rules_dir, monkeypatch):
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        ctx = _make_context(str(tmp_path), [path])
        monkeypatch.setattr(shutil, "which", lambda _: None)
        gate = LintGate(rules_dir=dual_backend_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert "semgrep" in result.message.lower()

    def test_ast_grep_missing_semgrep_still_works(self, tmp_path, dual_backend_rules_dir, monkeypatch):
        """When ast-grep is missing, Semgrep violations are still reported."""
        original_which = shutil.which
        monkeypatch.setattr(shutil, "which", lambda cmd: None if cmd in ("sg", "ast-grep") else original_which(cmd))
        path = _make_file(tmp_path, "widget.py", "items = []\nitems.append(1)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=dual_backend_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-list-append" in i for i in result.issues)
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_lint_gate.py::TestLintGateDualBackend -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_lint_gate.py
git commit -m "test: add dual-backend integration tests for LintGate"
```

---

### Task 9: Update Install Script

**Files:**
- Modify: `install-governor.sh`

- [ ] **Step 1: Add Semgrep dependency check**

After the existing `beniget` check (line 29), add:

```bash
if ! command -v semgrep > /dev/null 2>&1; then
  echo "Error: semgrep is required but not found. Install with: pip install semgrep" >&2
  exit 1
fi
```

- [ ] **Step 2: Update the lint rules installation section**

Replace lines 84-89:

```bash
# --- install lint rules ---
echo "Installing lint rules..."
LINT_DIR="$HOME/.claude/plugins/context-injector/scripts/lint/rules"
mkdir -p "$LINT_DIR"
cp "$PLUGIN_DIR/scripts/lint/sgconfig.yml" "$HOME/.claude/plugins/context-injector/scripts/lint/"
cp "$PLUGIN_DIR/scripts/lint/rules/"*.yml "$LINT_DIR/"
```

With:

```bash
# --- install lint rules ---
echo "Installing lint rules..."
LINT_DIR="$HOME/.claude/plugins/context-injector/scripts/lint"
mkdir -p "$LINT_DIR/rules"
cp "$PLUGIN_DIR/scripts/lint/sgconfig.yml" "$LINT_DIR/"
cp "$PLUGIN_DIR/scripts/lint/semgrep-rules.yml" "$LINT_DIR/"
cp "$PLUGIN_DIR/scripts/lint/rules/"*.yml "$LINT_DIR/rules/"
```

- [ ] **Step 3: Commit**

```bash
git add install-governor.sh
git commit -m "feat: add semgrep dependency check and copy semgrep-rules.yml in installer"
```

---

### Task 10: Update README and Deploy

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the LintGate section in README**

Update the LintGate description to mention the dual-backend architecture, the Semgrep dependency, the rule count (26 Semgrep + 2 ast-grep = 28 total), and the new `no-optional-none` rule.

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass. Note the total count.

- [ ] **Step 3: Deploy changed files to plugin directory**

```bash
cp gates/lint.py ~/.claude/plugins/context-injector/gates/
cp scripts/lint/semgrep-rules.yml ~/.claude/plugins/context-injector/scripts/lint/
cp scripts/lint/rules/no-deep-nesting.yml ~/.claude/plugins/context-injector/scripts/lint/rules/
cp scripts/lint/rules/no-loop-mutation.yml ~/.claude/plugins/context-injector/scripts/lint/rules/
# Remove old ast-grep rules from plugin dir
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-list-*.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-dict-*.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-set-*.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-subscript-*.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-attribute-*.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-local-*.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-bare-except.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-except-exception.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-is-none.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-is-not-none.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-print.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-static-method.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-relative-import.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-setitem-call.yml
rm -f ~/.claude/plugins/context-injector/scripts/lint/rules/no-none-default-param.yml
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for Semgrep migration and no-optional-none rule"
```
