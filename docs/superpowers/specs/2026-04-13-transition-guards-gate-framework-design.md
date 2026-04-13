# Transition Guards & Gate Framework

## Goal

Add a gate framework to the governor that evaluates work quality at transition boundaries, with a test quality gate as the first implementation. Gates are transition guards — they run when a transition is about to fire and can block it, force a self-review, or let it through. Replace the JSONL audit trail with a TinyDB document store for queryable audit history.

## Architecture

### Gate Abstraction

A `Gate` is a check that runs when a state machine transition is about to fire. It inspects the work done during the current state and decides whether the transition should proceed.

**Evaluation flow:**

```
preconditions pass? → gates pass? → transition fires → auto-advance
```

Preconditions answer "did you do the work?" Gates answer "is the work good enough?"

**Base classes:**

```python
# gates/base.py

class GateVerdict(str, Enum):
    PASS = "pass"       # Transition proceeds
    FAIL = "fail"       # Transition blocked (hard or soft, per softness)
    REVIEW = "review"   # Inject a review prompt — agent must self-review, then retry

class GateResult:
    verdict: GateVerdict
    message: str | None   # Human-readable explanation
    issues: list[str]     # Machine-readable issue identifiers

class GateContext:
    state_name: str              # Current state being exited
    transition_name: str         # Transition being attempted
    recent_tools: list[str]      # Tool signatures since last transition
    recent_files: list[str]      # Files written/edited since last transition
    machine: GovernedMachine     # The active machine
    project_root: str            # For reading files off disk

class Gate:
    """Base class for transition guards."""
    name: str = "unnamed"

    def evaluate(self, context: GateContext) -> GateResult:
        raise NotImplementedError
```

### Machine Registration

Machine authors register gates declaratively via two new class dicts on `GovernedMachine`:

```python
class TDD(GovernedMachine):
    GUARDS = {
        "pytest_fail": [TestQualityGate],
        "pytest_pass": [],
    }

    # Controls whether gate failure = hard block or challenge
    GATE_SOFTNESS = {
        "test_quality": 0.1,   # Strict by default — override per project
    }
```

`GovernedMachine` base class gets:
- `GUARDS: dict[str, list[type[Gate]]]` — maps transition names to gate classes
- `GATE_SOFTNESS: dict[str, float]` — per-gate softness overrides
- `get_guards(transition_name) -> list[type[Gate]]` — accessor method
- `get_gate_softness(gate_name) -> float` — accessor with default fallback

### Governor Integration

The gate check slots into `Governor.trigger_transition()` between precondition check and the actual transition:

```python
def trigger_transition(self, event_name, ...):
    # ... existing precondition check ...

    # Run guards
    guards = self.machine.get_guards(event_name)
    for gate_cls in guards:
        gate = gate_cls()
        result = gate.evaluate(context)
        if result.verdict == GateVerdict.FAIL:
            softness = self.machine.get_gate_softness(gate.name)
            return self._gate_failure_response(gate, result, event_name, softness)
        if result.verdict == GateVerdict.REVIEW:
            return self._gate_review_response(gate, result, event_name)

    # ... existing transition fires ...
```

Gate failures feed into the existing graduated response system via `GATE_SOFTNESS`. A gate with softness 0.1 produces a hard block; softness 0.5 produces a challenge.

### GateContext Construction

The governor constructs `GateContext` from data it already tracks:

- `recent_tools` — already persisted in state (used for preconditions)
- `recent_files` — derived from `recent_tools` by extracting file paths from `Write(path)` and `Edit(path)` signatures. This requires a minor change: store the full file path in `recent_tools` instead of just the basename, for tool signatures that target files.
- `project_root` — `os.getcwd()` (same as context_dir derivation)
- `machine`, `state_name`, `transition_name` — directly available in the governor

No new state persistence is needed for gate context.

### Transcript Scanning Integration

The current `_check_transcript_for_pytest()` method fires transitions directly via `send()`, bypassing `trigger_transition()`. This means gates would never run for transcript-detected pytest results (which is the primary path for `pytest_fail` — PostToolUse doesn't fire on non-zero exit codes).

**Required change:** Refactor `_check_transcript_for_pytest()` to call `self.trigger_transition(event_name)` instead of `send()` directly. This routes transcript-detected pytest results through the same gate evaluation path as PostToolUse-detected results.

### Tool Signature Enhancement

The current governor stores tool signatures with basenames only (e.g., `Write(test_widget.py)`). Gates need full paths to read files from disk.

**Required change:** Store full file paths in `recent_tools` signatures: `Write(/abs/path/to/test_widget.py)`. The `_check_tool_against_state()` method continues to extract basenames for pattern matching — the change is additive.

## Test Quality Gate

The first concrete gate. Runs on `pytest_fail` transitions to evaluate whether the test the agent just wrote is structurally sound.

### Static Analysis Layer

Uses Python's `ast` module to parse recently-written test files and detect structural weaknesses.

**Hard violations (zero false positives, always blocked):**

| Pattern | Detection | Example |
|---|---|---|
| No assertions | Test function body contains no `assert` statements | `def test_foo(): result = f()` |
| Trivial assertions | `assert True`, `assert 1`, `assert "literal"` | `assert True` |
| Skip abuse | `pytest.skip()` in test body | `pytest.skip("not ready")` |
| Xfail abuse | `@pytest.mark.xfail` decorator or `pytest.xfail()` call | `@pytest.mark.xfail` |

**Soft violations (heuristic, may have legitimate uses — triggers LLM review):**

| Pattern | Detection | Example |
|---|---|---|
| None-only checks | All assertions only check `is not None` / `is None` | `assert result is not None` |
| Membership-only checks | All assertions only check `x in y` without value verification | `assert "key" in result` |
| Type-only checks | All assertions only check `isinstance()` | `assert isinstance(x, dict)` |
| No value comparisons | Assertions exist but none use `==`, `!=`, `>`, `<`, `>=`, `<=` against an expected value | `assert len(result) > 0` without checking content |
| Import overlap | Test imports production module and calls the same function on both sides of assertion (simple case only — full tautological detection deferred) | `from app import compute; assert compute(1) == compute(1)` |

**Implementation:**

```python
# gates/test_quality.py

class TestQualityGate(Gate):
    name = "test_quality"

    def evaluate(self, ctx: GateContext) -> GateResult:
        test_files = [f for f in ctx.recent_files if self._is_test_file(f)]
        if not test_files:
            return GateResult(GateVerdict.PASS)

        issues = []
        for path in test_files:
            source = open(path).read()
            tree = ast.parse(source)
            for func in self._extract_test_functions(tree):
                issues.extend(self._analyze_function(func, path))

        hard = [i for i in issues if i.severity == "hard"]
        soft = [i for i in issues if i.severity == "soft"]

        if hard:
            return GateResult(
                GateVerdict.FAIL,
                message=self._format_issues(hard),
                issues=[str(i) for i in hard],
            )
        if soft:
            return GateResult(
                GateVerdict.REVIEW,
                message=self._format_review_prompt(soft),
                issues=[str(i) for i in soft],
            )
        return GateResult(GateVerdict.PASS)

    @staticmethod
    def _is_test_file(path: str) -> bool:
        return os.path.basename(path).startswith("test_") and path.endswith(".py")

    def _extract_test_functions(self, tree: ast.Module) -> list[ast.FunctionDef]:
        """Extract all test_* functions, including those inside test classes."""
        funcs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    funcs.append(node)
        return funcs

    def _analyze_function(self, func, path):
        """Run all checks against a single test function."""
        # ... delegates to individual check methods ...
```

### AST Analysis Details

**Assertion extraction:** Walk the function body for `ast.Assert` nodes. Also detect `pytest.raises` context managers (these count as assertions).

**Trivial assertion detection:** Check if the `assert` test expression is a `ast.Constant` with a truthy value.

**Membership-only detection:** Check if ALL assertions in the function use `ast.Compare` with `ast.In` or `ast.NotIn` operators, with no assertions using `ast.Eq`, `ast.NotEq`, `ast.Lt`, `ast.Gt`, etc.

**Tautological detection:** Compare the function's imports against the test file's imports. If the test function calls the same callable it imports from the production module to compute the expected value, flag it. This is detected by tracking `ast.Call` nodes on both sides of an assertion's comparison.

### Severity Classification

Hard violations are structurally invalid tests — they can never meaningfully constrain behavior. These are always flagged regardless of project configuration.

Soft violations are patterns that are *usually* weak but can be legitimate:
- `assert "key" in result` might be fine for testing API response shape
- `assert isinstance(x, Widget)` might be the right check for a factory
- `assert result is not None` might be the first of several assertions

The soft → review path forces the agent to justify or strengthen, rather than hard-blocking.

## LLM-as-Judge Integration

### Review Flow

When a gate returns `REVIEW`, the governor:

1. Does NOT fire the transition
2. Returns a response with `action: "review"` and the gate's review prompt as `message`
3. The hook shell script translates this into a Claude Code hook response that injects the message into the conversation

The agent sees a system-injected message like:

> **GATE: test_quality** flagged potential issues in `test_widget.py::test_create_widget`:
> - Assertions only check membership (`assert "name" in result`) without verifying values
> - No assertion compares against an expected value
>
> Review this test — does it actually constrain the behavior you're implementing? If intentional, run pytest again to retry. Otherwise, strengthen the assertions first.

The agent then either:
- Strengthens the test and runs pytest again (gate re-evaluates the updated file)
- Runs pytest again without changes (retry — gate sees the same issues)

### Retry Limit and Escalation

Track gate review attempts in persisted state:

```python
# In governor state file
"gate_attempts": {
    "test_quality": {
        "count": 1,
        "last_file": "tests/test_widget.py",
        "last_issues": ["membership_only_assertion:15"]
    }
}
```

- **Attempt 1:** Return `review` with the prompt
- **Attempt 2:** Return `review` with escalated wording ("This is the second time this gate flagged the same issue...")
- **Attempt 3+:** The gate still returns its verdict, but the governor overrides to `allow` with a warning. The agent is not blocked forever — but the audit records that the gate was overridden.

Gate attempt counters reset when:
- The transition fires successfully (agent fixed the issue)
- The file content changes (agent modified the test — re-evaluate fresh)
- The state changes for any other reason

### Hook Response Format

The `review` action maps to the existing Claude Code hook response structure:

```json
{
  "action": "review",
  "message": "GATE: test_quality flagged...",
  "current_state": "writing_tests",
  "transition": null,
  "context_to_inject": [],
  "gate_results": {
    "test_quality": {
      "verdict": "review",
      "issues": ["membership_only_assertion:test_widget.py:15"],
      "attempt": 1
    }
  }
}
```

The shell hook translates `action: "review"` to a hook response that proceeds (does not block the tool call) but injects the gate message as system context. This mirrors how `action: "remind"` works in the graduated response system.

## Gate Framework — Making New Gates Cheap

### File Structure

```
gates/
  __init__.py           # Exports Gate, GateResult, GateVerdict, GateContext
  base.py               # Base classes
  test_quality.py       # First concrete gate
```

### Adding a New Gate

A new gate is a single Python file with a class extending `Gate`:

```python
# gates/diff_size.py
class DiffSizeGate(Gate):
    name = "diff_size"
    max_lines = 100

    def evaluate(self, ctx: GateContext) -> GateResult:
        result = subprocess.run(
            ["git", "diff", "--stat", "--cached"],
            capture_output=True, text=True, cwd=ctx.project_root,
        )
        lines_changed = self._parse_total_lines(result.stdout)
        if lines_changed > self.max_lines:
            return GateResult(
                GateVerdict.FAIL,
                message=f"Diff is {lines_changed} lines (limit: {self.max_lines}). "
                        f"Commit your current work before continuing.",
                issues=[f"diff_size:{lines_changed}"],
            )
        return GateResult(GateVerdict.PASS)
```

Register by adding to a machine's `GUARDS` dict:

```python
GUARDS = {
    "pytest_fail": [TestQualityGate],
    "impl_complete": [DiffSizeGate],
}
```

### Future Gates (not in scope, but trivial to add)

| Gate | Transition | What it checks |
|---|---|---|
| `DiffSizeGate` | `impl_complete` | Lines changed per cycle |
| `CoverageRegressionGate` | `pytest_pass` | Coverage didn't drop |
| `CommitHygieneGate` | `start_next_test` | Work was committed before next cycle |
| `ScopeContainmentGate` | any | Only declared files were touched |
| `BranchHygieneGate` | any commit transition | Not on main/master |

## Audit Trail — TinyDB

### Migration from JSONL

Replace the existing JSONL append log with a TinyDB document store. One database file per project.

**Location:** `$CTX_AUDIT_DIR/<project_hash>.audit.json`

**Dependency:** `tinydb>=4.0.0` (pure Python, no native extensions)

### Document Structure

Documents are schema-free. Convention, not enforcement:

```python
{
    "timestamp": "2026-04-13T10:30:00Z",
    "session_id": "abc123",
    "machine": "TDD",
    "type": "transition",          # transition | tool_eval | gate_eval
    "from_state": "writing_tests",
    "to_state": "red",
    "trigger": "pytest_result",
    "tool_name": "Bash",
    "tool_input_summary": "pytest tests/ -v",
    "softness": 1.0,
    "action": "allow",
    "message": null,
    "context_injected": [],

    # Gate-specific fields (only on type=gate_eval)
    "gate": "test_quality",
    "verdict": "review",
    "issues": ["membership_only_assertion:test_widget.py:15"],
    "attempt": 1
}
```

New fields can appear at any time — no migrations needed. Gates add their own fields to audit documents.

### Audit API

```python
# governor/audit.py

from tinydb import TinyDB, where

class AuditStore:
    def __init__(self, db_path: str):
        self.db = TinyDB(db_path)

    def write(self, entry: dict) -> int:
        """Append an audit document. Returns the document ID."""
        return self.db.insert(entry)

    def query(self, **filters) -> list[dict]:
        """Query audit entries by field values."""
        q = None
        for key, value in filters.items():
            condition = where(key) == value
            q = condition if q is None else q & condition
        return self.db.search(q) if q else self.db.all()

    def gate_failures(self, gate_name: str = None, since: str = None) -> list[dict]:
        """Query gate evaluations with non-pass verdicts."""
        q = where("type") == "gate_eval"
        if gate_name:
            q = q & (where("gate") == gate_name)
        if since:
            q = q & (where("timestamp") >= since)
        return self.db.search(q & (where("verdict") != "pass"))
```

### Query CLI

```bash
# All gate failures this week
governor audit --gate test_quality --verdict fail --since 7d

# All transitions in current session
governor audit --type transition --session current

# Recent gate evaluations
governor audit --type gate_eval --limit 20

# Full audit dump
governor audit --all
```

### Migration Path

The existing `write_audit_entry()` function in `governor/audit.py` changes from:

```python
# Before: JSONL append
def write_audit_entry(audit_file, entry):
    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
```

To:

```python
# After: TinyDB insert
def write_audit_entry(audit_file, entry):
    db = TinyDB(audit_file)
    db.insert(entry)
```

The function signature stays the same — callers pass a dict. The `audit_file` path changes extension from `.jsonl` to `.audit.json`. Existing JSONL files are not migrated — they remain readable but the governor writes to TinyDB going forward.

## Scope

### In scope (this spec)

1. `gates/` package with `Gate`, `GateResult`, `GateVerdict`, `GateContext` base classes
2. `TestQualityGate` with AST-based static analysis (hard + soft violations)
3. `GUARDS` and `GATE_SOFTNESS` dicts on `GovernedMachine`
4. Governor integration: gate evaluation in `trigger_transition()` and `_handle_declaration()`
5. LLM-as-judge flow: `review` verdict, retry tracking, escalation after max attempts
6. TinyDB audit trail replacing JSONL
7. `governor audit` query CLI
8. Tests for all of the above

### Out of scope (future work)

- DiffSizeGate, CoverageRegressionGate, and other concrete gates beyond TestQualityGate
- Full tautological test detection (complex AST analysis involving dataflow — defer to second iteration; simple import-overlap detection IS in scope)
- Audit data visualization or dashboards
- Migration tooling for existing JSONL audit files

## Dependencies

- `tinydb>=4.0.0` (new — pure Python document store)
- `python-statemachine>=3.0.0` (existing)
- `pytest>=8.0` (existing, dev only)
