# LintGate Semgrep Migration

## Goal

Migrate all losslessly-portable ast-grep lint rules to Semgrep, add a new `no-optional-none` rule, and update LintGate to run both Semgrep and ast-grep as dual backends. Delete migrated ast-grep rule files.

## Architecture

LintGate becomes a dual-backend gate. It runs Semgrep for 26 rules (25 migrated + 1 new), then ast-grep for the 2 rules that require tree-sitter-specific features (`stopBy:`, `has:` with `kind:`). Results are merged into a single violation list. Semgrep is a hard dependency — the gate fails with a clear error if the binary is missing.

## Rule Classification

### Migrating to Semgrep (25 rules)

These use only `pattern:`, `any:` (maps to `pattern-either:`), `not:` (maps to `pattern-not:`), or `inside: kind:` (maps to `pattern-inside:`).

| Rule ID | ast-grep features | Semgrep mapping |
|---------|-------------------|-----------------|
| no-list-append | `pattern:` | `pattern:` |
| no-list-extend | `pattern:` | `pattern:` |
| no-list-insert | `pattern:` | `pattern:` |
| no-list-pop | `pattern:` | `pattern:` |
| no-list-remove | `pattern:` | `pattern:` |
| no-dict-clear | `pattern:` | `pattern:` |
| no-dict-update | `pattern:` | `pattern:` |
| no-dict-setdefault | `pattern:` | `pattern:` |
| no-set-add | `pattern:` | `pattern:` |
| no-set-discard | `pattern:` | `pattern:` |
| no-subscript-mutation | `pattern:` | `pattern:` |
| no-subscript-del | `pattern:` | `pattern:` |
| no-is-none | `pattern:` | `pattern:` |
| no-is-not-none | `pattern:` | `pattern:` |
| no-print | `pattern:` | `pattern:` |
| no-static-method | `pattern:` | `pattern:` |
| no-bare-except | `pattern:` (multiline) | `pattern:` |
| no-except-exception | `pattern:` (multiline) | `pattern:` |
| no-relative-import | `any:` | `pattern-either:` |
| no-setitem-call | `any:` | `pattern-either:` |
| no-subscript-augmented-mutation | `any:` | `pattern-either:` |
| no-subscript-tuple-mutation | `any:` | `pattern-either:` |
| no-attribute-augmented-mutation | `any:` | `pattern-either:` |
| no-local-augmented-mutation | `any:` + `not:` + `has: kind:` + `field:` | `pattern-either:` + `pattern-not:` |
| no-none-default-param | `pattern:` + `inside: kind:` | `pattern:` + `pattern-inside:` |

### New Semgrep Rule (1 rule)

| Rule ID | Description |
|---------|-------------|
| no-optional-none | Bans `Optional[X]`, `X \| None`, `None \| X`, `Union[X, None]`, `Union[None, X]` |

### Staying in ast-grep (2 rules)

These require `stopBy: function_definition` to prevent false positives from nested function definitions. Semgrep has no equivalent.

| Rule ID | Reason |
|---------|--------|
| no-deep-nesting | `kind:` + `has:` + `stopBy: function_definition` |
| no-loop-mutation | `kind:` + `has:` + `stopBy: function_definition` |

## File Layout After Migration

```
scripts/lint/
  sgconfig.yml              # unchanged, points to rules/
  semgrep-rules.yml         # NEW: 26 Semgrep rules
  rules/
    no-deep-nesting.yml     # stays (ast-grep)
    no-loop-mutation.yml    # stays (ast-grep)
```

25 ast-grep rule files are deleted from `rules/`. `sgconfig.yml` continues to work — it scans `rules/` which now contains only the 2 remaining files.

## Semgrep Rule Format

All 26 rules live in a single `semgrep-rules.yml` file under a top-level `rules:` key. Each rule has:

```yaml
rules:
  - id: <rule-id>
    pattern: <pattern>              # or patterns: with pattern-either:/pattern-not:
    message: <message>
    severity: WARNING
    languages: [python]
```

### Mapping Details

**Simple pattern rules** (16 rules): Direct 1:1 mapping.

```yaml
# ast-grep
id: no-list-append
rule:
  pattern: $OBJ.append($$$ARGS)

# Semgrep equivalent
- id: no-list-append
  pattern: $OBJ.append(...)
  languages: [python]
```

Note: ast-grep's `$$$ARGS` (variadic metavar) maps to Semgrep's `...` (ellipsis operator).

**`any:` combinator rules** (7 rules): Map to `pattern-either:`.

```yaml
# ast-grep
rule:
  any:
    - pattern: from . import $NAME
    - pattern: from ..$MOD import $NAME

# Semgrep equivalent
patterns:
  - pattern-either:
      - pattern: from . import $NAME
      - pattern: from ..$MOD import $NAME
```

**`not:` with `has: kind:` rule** (`no-local-augmented-mutation`): The ast-grep rule matches augmented assignments (`$VAR += $VAL` etc.) but excludes those where the left side is an attribute or subscript. In Semgrep, this becomes `pattern-either:` for each operator combined with `pattern-not:` entries for `$OBJ.$ATTR += $VAL` and `$OBJ[$KEY] += $VAL` forms.

```yaml
- id: no-local-augmented-mutation
  patterns:
    - pattern-either:
        - pattern: $VAR += $VAL
        - pattern: $VAR -= $VAL
        # ... 10 more operators
    - pattern-not: $OBJ.$ATTR += $VAL
    - pattern-not: $OBJ.$ATTR -= $VAL
    # ... 10 more operators
    - pattern-not: $OBJ[$KEY] += $VAL
    - pattern-not: $OBJ[$KEY] -= $VAL
    # ... 10 more operators
```

**`inside: kind:` rule** (`no-none-default-param`): Maps to `pattern-inside:`.

```yaml
- id: no-none-default-param
  patterns:
    - pattern: $PARAM = None
    - pattern-inside: |
        def $F(...):
            ...
```

**New rule** (`no-optional-none`):

```yaml
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

## LintGate Changes

### `gates/lint.py`

The `evaluate()` method runs both backends:

1. Find Semgrep binary — **required**. If missing, return `GateResult(FAIL, "semgrep binary not found")`
2. Find ast-grep binary — optional (only needed for the 2 remaining rules). If missing, skip ast-grep
3. Resolve rules directory (unchanged logic)
4. Run Semgrep: `semgrep scan --config <rules-dir>/semgrep-rules.yml --json <files>`
5. Run ast-grep: `sg scan --json --config <rules-dir>/sgconfig.yml <files>` (same as current)
6. Parse and normalize both outputs into the same `{ruleId, file, line, message, source}` dict format
7. Merge violation lists, return combined result

### New methods

- `_find_semgrep() -> str | None` — `shutil.which("semgrep")`
- `_run_semgrep(semgrep_path, rules_file, files) -> list[dict]` — runs Semgrep, parses its JSON output

### Semgrep JSON output format

```json
{
  "results": [
    {
      "check_id": "no-list-append",
      "path": "foo.py",
      "start": {"line": 10, "col": 5},
      "extra": {
        "message": "...",
        "lines": "  items.append(x)"
      }
    }
  ]
}
```

This normalizes to the same internal dict: `{ruleId: check_id, file: path, line: start.line, message: extra.message, source: extra.lines}`.

## Install Script Changes

`install-governor.sh`:

- Add `semgrep` binary check at startup, fail with error message if missing
- Copy `semgrep-rules.yml` to the plugin lint directory alongside `sgconfig.yml` and `rules/`

## Tests

### Strategy

Every rule gets a dedicated test class with FAIL and PASS cases. Tests use temporary Python files and invoke the appropriate backend (Semgrep or ast-grep) directly.

### Semgrep Rule Tests (26 test classes)

Each test class follows this pattern:

```python
class TestNoListAppend:
    def test_fail_append_call(self, semgrep_rules):
        # Write code with .append() call, assert violation found
    def test_pass_no_append(self, semgrep_rules):
        # Write clean code, assert no violations
```

Specific test coverage per rule:

| Rule | FAIL cases | PASS cases |
|------|------------|------------|
| no-list-append | `.append()` call | No `.append()` |
| no-list-extend | `.extend()` call | No `.extend()` |
| no-list-insert | `.insert()` call | No `.insert()` |
| no-list-pop | `.pop()` call | No `.pop()` |
| no-list-remove | `.remove()` call | No `.remove()` |
| no-dict-clear | `.clear()` call | No `.clear()` |
| no-dict-update | `.update()` call | No `.update()` |
| no-dict-setdefault | `.setdefault()` call | No `.setdefault()` |
| no-set-add | `.add()` call | No `.add()` |
| no-set-discard | `.discard()` call | No `.discard()` |
| no-subscript-mutation | `obj[k] = v` | No subscript assignment |
| no-subscript-del | `del obj[k]` | No subscript delete |
| no-subscript-augmented-mutation | `obj[k] += v` (all 12 operators) | No subscript augmented ops |
| no-subscript-tuple-mutation | `obj[k], obj[j] = ...` | No tuple subscript assignment |
| no-attribute-augmented-mutation | `obj.x += v` (all 12 operators) | No attribute augmented ops |
| no-local-augmented-mutation | `x += v` (local var, all 12 operators) | `obj.x += v` (attribute, should pass); `obj[k] += v` (subscript, should pass) |
| no-setitem-call | `obj.__setitem__(k, v)` | No `__setitem__` call |
| no-is-none | `x is None` | `x is not None`; `x == y` |
| no-is-not-none | `x is not None` | `x is None`; `x != y` |
| no-print | `print(...)` | No print call |
| no-static-method | `@staticmethod` | `@classmethod`; no decorator |
| no-bare-except | `except:` (no type) | `except ValueError:` |
| no-except-exception | `except Exception:` | `except ValueError:` |
| no-relative-import | `from . import x`; `from ..mod import x` | `from mod import x`; `import mod` |
| no-none-default-param | `def f(x=None):` | `def f(x=0):` ; `x = None` outside function params |
| no-optional-none | `Optional[str]`; `str \| None`; `None \| str`; `Union[str, None]`; `Union[None, str]` | `str`; `int`; `Union[str, int]` (no None) |

### ast-grep Rule Tests (2 test classes — existing)

| Rule | FAIL cases | PASS cases |
|------|------------|------------|
| no-deep-nesting | for-in-for, if-in-for, for-in-if, if-in-if, triple nesting | flat for, flat if, for-in-nested-function (boundary) |
| no-loop-mutation | append/extend/subscript-assign/augmented-assign/del/set.add in for | no mutation in for, mutation outside for |

### Integration Test (1 test class)

- `TestLintGateDualBackend`:
  - Test: file with both a Semgrep violation (e.g., `.append()`) and an ast-grep violation (e.g., nested for) — gate returns merged violations from both
  - Test: Semgrep-only violation — gate returns it
  - Test: ast-grep-only violation — gate returns it
  - Test: no violations — gate passes
  - Test: Semgrep binary missing — gate fails with clear error message
  - Test: ast-grep binary missing but Semgrep present — Semgrep violations still reported, ast-grep skipped gracefully

### Test Fixtures

- `semgrep_rules` fixture: points to the `semgrep-rules.yml` file
- `nesting_rules_dir` fixture: existing, points to ast-grep rules
- `loop_mutation_rules_dir` fixture: existing, points to ast-grep rules
- Helper to run Semgrep on a temp file and return violations (parallel to existing `_run_sg` test helper pattern)
