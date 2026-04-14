# Lint Rules Extraction Design

## Goal

Extract Semgrep + ast-grep lint rules, LintGate, and ReassignmentGate into a standalone repo (`python-fp-lint`) that can be used independently or consumed by context-injector as a git submodule.

## Motivation

- Reuse the same rules across multiple projects
- Allow others to use the lint rules without adopting the governor
- Rules and gate logic evolve independently from the governor

## New Repo: `python-fp-lint`

### Package Structure

```
python-fp-lint/
├── pyproject.toml              # Python package, pip-installable
├── semgrep-rules.yml           # 26 Semgrep rules
├── sgconfig.yml                # ast-grep config
├── rules/                      # ast-grep rules
│   ├── no-deep-nesting.yml
│   └── no-loop-mutation.yml
├── python_fp_lint/             # Python package
│   ├── __init__.py             # Exports LintGate, ReassignmentGate, LintResult
│   ├── lint_gate.py            # LintGate class (moved from gates/lint.py)
│   ├── reassignment_gate.py    # ReassignmentGate class (moved from gates/reassignment.py)
│   ├── result.py               # LintResult dataclass
│   └── patterns_report.py      # Moved from scripts/lint/patterns_report.py
└── tests/
    ├── test_lint_gate.py       # Moved from context-injector
    └── test_reassignment_gate.py  # Moved from context-injector
```

### Result Type

`python-fp-lint` defines its own result type — no gate abstraction:

```python
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

LintGate and ReassignmentGate both return `LintResult` instead of `GateResult`. The new repo has no concept of "gates" — it's a lint tool that returns lint results.

### LintGate Changes

The class moves as-is, with these adjustments:

- No longer inherits from `GateBase`
- `evaluate(changed_files, project_root)` returns `LintResult` instead of `GateResult`
- Rule file discovery uses paths relative to the package (`__file__`), since the rule files live alongside the Python code
- No `config.json` fallback — the package knows where its own rules are

### ReassignmentGate Changes

Same adjustments:

- No longer inherits from `GateBase`
- `evaluate(changed_files, project_root)` returns `LintResult`
- Standalone — no governor dependency

### CLI Entry Point

Standalone usage without the governor:

```bash
# Run all checks on changed files
python -m python_fp_lint check file1.py file2.py

# Run only semgrep rules
python -m python_fp_lint check --semgrep-only file1.py

# Run only reassignment checks
python -m python_fp_lint check --reassignment-only file1.py
```

### Dependencies

Runtime:
- `beniget>=0.5.0` (for ReassignmentGate)

External tools (not Python deps):
- `semgrep` — required for lint rules
- `ast-grep` (`sg`) — optional for 2 rules

Dev:
- `pytest>=8.0`

### Distribution

- Git repo on GitHub (`avishek-sen-gupta/python-fp-lint`)
- pip-installable via `pyproject.toml` (PyPI publication optional, later)
- Usable as a git submodule

## Changes to context-injector

### Submodule

`scripts/lint/` becomes a git submodule pointing at `python-fp-lint`:

```bash
git submodule add https://github.com/avishek-sen-gupta/python-fp-lint.git scripts/lint
```

The submodule replaces the current `scripts/lint/` directory contents. Rule files live at the same paths (`scripts/lint/semgrep-rules.yml`, etc.) so existing config.json references remain valid.

### Import Path

`scripts/lint/` is added to `sys.path` so that `from python_fp_lint import LintGate` works. This matches standalone usage — same import whether pip-installed or used via submodule.

The governor already manipulates `sys.path` to find its modules. Adding one more path follows the existing pattern.

### Gate Adapters

`gates/lint.py` and `gates/reassignment.py` become thin adapters:

```python
# gates/lint.py
from gates.base import GateBase, GateResult
from python_fp_lint import LintGate as _LintGate

class LintGate(GateBase):
    def evaluate(self, changed_files, project_root):
        lint = _LintGate()
        result = lint.evaluate(changed_files, project_root)
        if result.passed:
            return GateResult.pass_result()
        return GateResult.fail(
            [f"{v.file}:{v.line} [{v.rule}] {v.message}" for v in result.violations]
        )
```

```python
# gates/reassignment.py
from gates.base import GateBase, GateResult
from python_fp_lint import ReassignmentGate as _ReassignmentGate

class ReassignmentGate(GateBase):
    def evaluate(self, changed_files, project_root):
        gate = _ReassignmentGate()
        result = gate.evaluate(changed_files, project_root)
        if result.passed:
            return GateResult.pass_result()
        return GateResult.fail(
            [f"{v.file}:{v.line} [{v.rule}] {v.message}" for v in result.violations]
        )
```

### install-governor.sh

Updated to:
1. Initialize/update the submodule: `git submodule update --init scripts/lint`
2. Copy from the submodule path (same paths, no change to copy logic)
3. Still writes `config.json` with `lint_rules_dir` pointing to the plugin's installed copy

### Tests

- `tests/test_lint_gate.py` and `tests/test_reassignment_gate.py` move to `python-fp-lint`
- Context-injector keeps `tests/test_governor_gates.py` (integration: governor wires gates correctly)
- New thin adapter tests in context-injector verify the `LintResult` → `GateResult` conversion

### pyproject.toml

Remove `beniget>=0.5.0` from context-injector's runtime deps (it moves to `python-fp-lint`). Add `python-fp-lint` as a dev dependency for running tests (the submodule provides it at runtime).

## No Changes

- `gates/base.py` (gate protocol stays in context-injector)
- `gates/test_quality.py` (governor-specific)
- Hook scripts, state machines, audit system
- TestQualityGate
- Governor gate wiring in machines (still references `LintGate` and `ReassignmentGate` from `gates/`)

## Out of Scope

- Publishing to PyPI (can be done later, structure supports it)
- Adding new lint rules (separate effort)
- Changing the gate protocol
- Moving TestQualityGate (it's governor-specific, not a lint tool)
