# Governor v4 Hook Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire governor_v4 engine into Claude Code hooks so `/governor` commands, tool blocking, and evidence capture work in live sessions.

**Architecture:** Shell hook scripts (deployed to `~/.claude/plugins/guvnah/hooks/`) call `python3 -m governor_v4 <subcommand>`. A `__main__.py` dispatcher lazy-imports handlers from `cli.py`. Lock file at `/tmp/ctx-governor/<hash>/active` gates all hooks. State persisted in `/tmp/ctx-governor/<hash>/`.

**Tech Stack:** Python 3.10+, existing governor_v4 package, shell hooks, pytest

---

## Context

Governor v4 is a library with no CLI or hook integration. This plan adds:
1. CLI entry point (`__main__.py` + `cli.py`) with subcommands: `init`, `evaluate`, `capture`, `prompt`
2. Four shell hook scripts for SessionStart, PreToolUse, PostToolUse, UserPromptSubmit
3. Deploy script to install to `~/.claude/plugins/guvnah/`

**Design spec:** `docs/superpowers/specs/2026-04-21-governor-v4-hook-integration-design.md`

**Existing v4 API (grounding — do not re-implement):**
- `GovernorV4(config, project_root, session_id, state_dir)` — engine
- `engine.evaluate(tool_name, tool_input) -> {"action": "allow"|"block", ...}`
- `engine.want_to_transition(target_state, evidence_key) -> {"action": "allow"|"deny", ...}`
- `engine.current_phase` — current state name
- `engine.locker` — EvidenceLocker instance
- `locker.store(evidence_type, tool_name, command, output, exit_code) -> key`
- `locker.retrieve(key) -> dict | None`
- `locker.keys() -> list[str]`
- `load_machine_from_json(source, from_file=True) -> MachineConfig`
- `match_capture_rule(tool_name, tool_arg, tool_pattern) -> bool` in primitives.py
- `NodeConfig.capture: list[CaptureRule]` — per-node capture rules
- `MachineConfig.find_edge(from_state, to_state) -> EdgeConfig | None`

---

## File Structure

**New files (governor_v4 package):**
- `governor_v4/__main__.py` — CLI dispatcher
- `governor_v4/cli.py` — shared setup + subcommand handlers

**New files (shell hooks):**
- `hooks/guvnah/session-start.sh`
- `hooks/guvnah/pre-tool-use.sh`
- `hooks/guvnah/post-tool-use.sh`
- `hooks/guvnah/user-prompt-submit.sh`

**New files (deploy):**
- `hooks/guvnah/install.sh` — copies hooks + machines to `~/.claude/plugins/guvnah/`

**New test files:**
- `tests/test_v4_cli.py` — CLI subcommand unit tests
- `tests/test_v4_hooks.py` — hook shell script integration tests

**Modified files:**
- None (v4 library code stays unchanged)

---

## Task 1: CLI Shared Setup (`cli.py`)

**Files:**
- Create: `governor_v4/cli.py`
- Test: `tests/test_v4_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_cli.py
import json
import os
import pytest
from governor_v4.cli import (
    get_state_dir,
    get_lock_file,
    is_governor_active,
    activate_governor,
    deactivate_governor,
    load_engine,
)


class TestStateDir:
    def test_state_dir_uses_session_hash(self):
        d = get_state_dir("abc123")
        assert d == "/tmp/ctx-governor/abc123"

    def test_state_dir_different_sessions(self):
        assert get_state_dir("a") != get_state_dir("b")


class TestLockFile:
    def test_lock_file_path(self):
        path = get_lock_file("abc123")
        assert path == "/tmp/ctx-governor/abc123/active"


class TestActivateDeactivate:
    def test_activate_creates_lock_and_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        lock = os.path.join(str(tmp_path), session_id, "active")
        assert os.path.exists(lock)
        # Lock file contains machine path
        with open(lock) as f:
            data = json.load(f)
        assert data["machine"] == machine_path

    def test_deactivate_removes_lock_and_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        deactivate_governor(session_id)
        lock = os.path.join(str(tmp_path), session_id, "active")
        assert not os.path.exists(lock)

    def test_is_active_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        assert is_governor_active(session_id) is True

    def test_is_active_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        assert is_governor_active("nonexistent") is False


class TestLoadEngine:
    def test_load_engine_returns_governor(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        engine = load_engine(session_id)
        assert engine is not None
        assert engine.current_phase == "writing_tests"

    def test_load_engine_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        engine = load_engine("nonexistent")
        assert engine is None

    def test_load_engine_restores_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        session_id = "test-sess"
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor(session_id, machine_path)
        # Transition to advance state
        engine1 = load_engine(session_id)
        engine1.want_to_transition("fixing_tests", None)
        # Reload — should restore
        engine2 = load_engine(session_id)
        assert engine2.current_phase == "fixing_tests"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_cli.py -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/cli.py
"""CLI shared setup: state dirs, lock files, engine loading."""

import json
import os
import shutil

from governor_v4.engine import GovernorV4
from governor_v4.loader import load_machine_from_json

_STATE_ROOT = "/tmp/ctx-governor"


def get_state_dir(session_id: str) -> str:
    return os.path.join(_STATE_ROOT, session_id)


def get_lock_file(session_id: str) -> str:
    return os.path.join(get_state_dir(session_id), "active")


def is_governor_active(session_id: str) -> bool:
    return os.path.exists(get_lock_file(session_id))


def activate_governor(session_id: str, machine_path: str) -> GovernorV4:
    """Create lock file, load machine, init engine, save state."""
    state_dir = get_state_dir(session_id)
    os.makedirs(state_dir, exist_ok=True)

    # Write lock file with machine path
    with open(get_lock_file(session_id), "w") as f:
        json.dump({"machine": machine_path}, f)

    config = load_machine_from_json(machine_path, from_file=True)
    engine = GovernorV4(
        config=config,
        session_id=session_id,
        state_dir=state_dir,
    )
    engine._save_phase()
    return engine


def deactivate_governor(session_id: str) -> None:
    """Remove lock file and state directory."""
    state_dir = get_state_dir(session_id)
    if os.path.exists(state_dir):
        shutil.rmtree(state_dir)


def load_engine(session_id: str) -> GovernorV4 | None:
    """Load engine from persisted state. Returns None if not active."""
    lock = get_lock_file(session_id)
    if not os.path.exists(lock):
        return None

    with open(lock) as f:
        data = json.load(f)

    machine_path = data["machine"]
    state_dir = get_state_dir(session_id)
    config = load_machine_from_json(machine_path, from_file=True)
    return GovernorV4(
        config=config,
        session_id=session_id,
        state_dir=state_dir,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_cli.py -xvs`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/cli.py tests/test_v4_cli.py
git commit -m "feat(v4): add CLI shared setup with state dir and engine loading"
```

---

## Task 2: CLI Dispatcher (`__main__.py`)

**Files:**
- Create: `governor_v4/__main__.py`
- Modify: `tests/test_v4_cli.py` (add dispatch tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_v4_cli.py`:

```python
import subprocess
import sys


class TestMainDispatch:
    def test_no_args_prints_usage(self):
        result = subprocess.run(
            [sys.executable, "-m", "governor_v4"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "usage" in result.stderr.lower()

    def test_unknown_subcommand_fails(self):
        result = subprocess.run(
            [sys.executable, "-m", "governor_v4", "bogus"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_prompt_subcommand_exists(self):
        # Just test it doesn't crash with --help or minimal args
        result = subprocess.run(
            [sys.executable, "-m", "governor_v4", "prompt", "--session", "test"],
            input='{"prompt": "hello"}',
            capture_output=True, text=True,
        )
        # Should exit 0 — no /governor command in "hello"
        assert result.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_cli.py::TestMainDispatch -xvs`
Expected: FAIL (no `__main__.py`)

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/__main__.py
"""CLI entry point: python3 -m governor_v4 <subcommand>."""

import sys


def main():
    if len(sys.argv) < 2:
        print("usage: python3 -m governor_v4 <init|evaluate|capture|prompt>", file=sys.stderr)
        sys.exit(1)

    subcommand = sys.argv[1]

    if subcommand == "init":
        from governor_v4.cmd_init import run
        run(sys.argv[2:])
    elif subcommand == "evaluate":
        from governor_v4.cmd_evaluate import run
        run(sys.argv[2:])
    elif subcommand == "capture":
        from governor_v4.cmd_capture import run
        run(sys.argv[2:])
    elif subcommand == "prompt":
        from governor_v4.cmd_prompt import run
        run(sys.argv[2:])
    else:
        print(f"unknown subcommand: {subcommand}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_cli.py::TestMainDispatch -xvs`
Expected: First two pass; third will fail until `cmd_prompt` exists (deferred to Task 4)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/__main__.py tests/test_v4_cli.py
git commit -m "feat(v4): add CLI dispatcher with lazy subcommand imports"
```

---

## Task 3: `cmd_init` — SessionStart Handler

**Files:**
- Create: `governor_v4/cmd_init.py`
- Modify: `tests/test_v4_cli.py` (add init tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_v4_cli.py`:

```python
class TestCmdInit:
    def test_init_restore_active_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_init import run_init
        output = run_init("s1")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "writing_tests" in ctx

    def test_init_restore_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_init import run_init
        output = run_init("nonexistent")
        assert output is None

    def test_init_restore_includes_phase_and_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_init import run_init
        output = run_init("s1")
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "blocked" in ctx.lower() or "Write" in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_cli.py::TestCmdInit -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/cmd_init.py
"""SessionStart handler: restore engine state and inject phase context."""

import json
import sys

from governor_v4.cli import load_engine, is_governor_active


def run_init(session_id: str) -> str | None:
    """Restore engine and return hook JSON with phase context, or None if inactive."""
    if not is_governor_active(session_id):
        return None

    engine = load_engine(session_id)
    if not engine:
        return None

    node = engine._get_node()
    blocked = node.blocked_tools or []
    exceptions = node.allowed_exceptions or []

    ctx_parts = [f"Governor active: phase={engine.current_phase}"]
    if blocked:
        ctx_parts.append(f"Blocked tools: {', '.join(blocked)}")
    if exceptions:
        ctx_parts.append(f"Exceptions: {', '.join(exceptions)}")

    ctx = ". ".join(ctx_parts) + "."

    return json.dumps({
        "hookSpecificOutput": {
            "additionalContext": ctx,
        }
    })


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 init`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    output = run_init(session_id)
    if output:
        print(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_cli.py::TestCmdInit -xvs`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/cmd_init.py tests/test_v4_cli.py
git commit -m "feat(v4): add cmd_init SessionStart handler"
```

---

## Task 4: `cmd_evaluate` — PreToolUse Handler

**Files:**
- Create: `governor_v4/cmd_evaluate.py`
- Modify: `tests/test_v4_cli.py` (add evaluate tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_v4_cli.py`:

```python
class TestCmdEvaluate:
    def test_evaluate_allow(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Read", "tool_input": {"file_path": "main.py"}}
        output = run_evaluate("s1", hook_input)
        assert output is None  # allow = no output

    def test_evaluate_block(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Write", "tool_input": {"file_path": "main.py"}}
        output = run_evaluate("s1", hook_input)
        assert output is not None
        parsed = json.loads(output)
        assert parsed["decision"] == "block"
        assert "blocked" in parsed["reason"].lower()

    def test_evaluate_exception_allows(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Write", "tool_input": {"file_path": "test_foo.py"}}
        output = run_evaluate("s1", hook_input)
        assert output is None  # exception allows it

    def test_evaluate_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_evaluate import run_evaluate
        hook_input = {"tool_name": "Write", "tool_input": {"file_path": "main.py"}}
        output = run_evaluate("nonexistent", hook_input)
        assert output is None  # inactive = pass-through
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_cli.py::TestCmdEvaluate -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/cmd_evaluate.py
"""PreToolUse handler: evaluate tool call against current phase."""

import json
import sys

from governor_v4.cli import load_engine


def run_evaluate(session_id: str, hook_input: dict) -> str | None:
    """Evaluate a tool call. Returns block JSON or None (allow)."""
    engine = load_engine(session_id)
    if not engine:
        return None

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    result = engine.evaluate(tool_name, tool_input)
    if result["action"] == "block":
        return json.dumps({
            "decision": "block",
            "reason": result["message"],
        })
    return None


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 evaluate`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    hook_input = json.loads(sys.stdin.read())
    output = run_evaluate(session_id, hook_input)
    if output:
        print(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_cli.py::TestCmdEvaluate -xvs`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/cmd_evaluate.py tests/test_v4_cli.py
git commit -m "feat(v4): add cmd_evaluate PreToolUse handler"
```

---

## Task 5: `cmd_capture` — PostToolUse Handler

**Files:**
- Create: `governor_v4/cmd_capture.py`
- Modify: `tests/test_v4_cli.py` (add capture tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_v4_cli.py`:

```python
from governor_v4.primitives import match_capture_rule


class TestCmdCapture:
    def test_capture_matching_tool(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_output": "FAILED 2 tests",
            "tool_exit_code": 1,
        }
        output = run_capture("s1", hook_input)
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "evt_" in ctx

    def test_capture_non_matching_tool(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "main.py"},
            "tool_output": "file contents",
        }
        output = run_capture("s1", hook_input)
        assert output is None  # no capture rule matched

    def test_capture_stores_in_locker(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_path = os.path.join(
            os.path.dirname(__file__), "..", "machines", "tdd_v4.json"
        )
        activate_governor("s1", machine_path)

        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_output": "PASSED 5 tests",
            "tool_exit_code": 0,
        }
        output = run_capture("s1", hook_input)
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        # Extract key from context
        key = [w for w in ctx.split() if w.startswith("evt_")][0]

        # Verify it's in the locker
        engine = load_engine("s1")
        entry = engine.locker.retrieve(key)
        assert entry is not None
        assert entry["type"] == "pytest_output"

    def test_capture_inactive_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_capture import run_capture
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "tool_output": "output",
        }
        output = run_capture("nonexistent", hook_input)
        assert output is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_cli.py::TestCmdCapture -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/cmd_capture.py
"""PostToolUse handler: capture tool output as evidence."""

import json
import sys

from governor_v4.cli import load_engine
from governor_v4.primitives import match_capture_rule


def run_capture(session_id: str, hook_input: dict) -> str | None:
    """Match capture rules and store evidence. Returns hook JSON or None."""
    engine = load_engine(session_id)
    if not engine or not engine.locker:
        return None

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    tool_output = hook_input.get("tool_output", "")
    exit_code = hook_input.get("tool_exit_code")

    # Get the tool arg for matching
    if tool_name == "Bash":
        tool_arg = tool_input.get("command", "")
    elif tool_name in ("Write", "Edit"):
        tool_arg = tool_input.get("file_path", "")
    else:
        tool_arg = ""

    # Check capture rules for current node
    node = engine._get_node()
    for rule in node.capture:
        if match_capture_rule(tool_name, tool_arg, rule.tool_pattern):
            key = engine.locker.store(
                evidence_type=rule.evidence_type,
                tool_name=tool_name,
                command=tool_arg,
                output=tool_output,
                exit_code=exit_code,
            )
            return json.dumps({
                "hookSpecificOutput": {
                    "additionalContext": (
                        f"Evidence captured: {key} "
                        f"(type={rule.evidence_type}, phase={engine.current_phase}). "
                        f"Use '/governor transition <target> {key}' to request a state transition."
                    ),
                }
            })

    return None


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 capture`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    hook_input = json.loads(sys.stdin.read())
    output = run_capture(session_id, hook_input)
    if output:
        print(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_cli.py::TestCmdCapture -xvs`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/cmd_capture.py tests/test_v4_cli.py
git commit -m "feat(v4): add cmd_capture PostToolUse handler"
```

---

## Task 6: `cmd_prompt` — UserPromptSubmit Handler

**Files:**
- Create: `governor_v4/cmd_prompt.py`
- Modify: `tests/test_v4_cli.py` (add prompt tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_v4_cli.py`:

```python
class TestCmdPrompt:
    def test_no_governor_command_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        from governor_v4.cmd_prompt import run_prompt
        output = run_prompt("s1", "just a normal prompt")
        assert output is None

    def test_governor_start_activates(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        # Need machines dir accessible
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        output = run_prompt("s1", "/governor tdd")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "writing_tests" in ctx
        assert is_governor_active("s1")

    def test_governor_off_deactivates(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        output = run_prompt("s1", "/governor off")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "deactivated" in ctx.lower()
        assert not is_governor_active("s1")

    def test_governor_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        output = run_prompt("s1", "/governor status")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "writing_tests" in ctx
        assert "fixing_tests" in ctx  # available transition target

    def test_governor_transition(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        # Activate and store some evidence
        run_prompt("s1", "/governor tdd")
        engine = load_engine("s1")
        key = engine.locker.store("pytest_output", "Bash", "pytest", "FAILED", 1)

        output = run_prompt("s1", f"/governor transition fixing_tests {key}")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "fixing_tests" in ctx

    def test_governor_transition_denied(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        # No evidence — should deny
        output = run_prompt("s1", "/governor transition fixing_tests")
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "deny" in ctx.lower() or "require" in ctx.lower()

    def test_governor_evidence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        run_prompt("s1", "/governor tdd")
        engine = load_engine("s1")
        key = engine.locker.store("pytest_output", "Bash", "pytest", "FAILED", 1)

        output = run_prompt("s1", "/governor evidence")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert key in ctx
        assert "pytest_output" in ctx

    def test_governor_unknown_machine(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cmd_prompt import run_prompt
        output = run_prompt("s1", "/governor nonexistent")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "not found" in ctx.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_cli.py::TestCmdPrompt -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/cmd_prompt.py
"""UserPromptSubmit handler: parse /governor commands."""

import json
import os
import sys

from governor_v4.cli import (
    activate_governor,
    deactivate_governor,
    is_governor_active,
    load_engine,
)

_MACHINE_DIR = os.path.expanduser("~/.claude/plugins/guvnah/machines")


def _hook_output(ctx: str) -> str:
    return json.dumps({"hookSpecificOutput": {"additionalContext": ctx}})


def _available_machines() -> list[str]:
    if not os.path.isdir(_MACHINE_DIR):
        return []
    return [
        f.removesuffix(".json")
        for f in os.listdir(_MACHINE_DIR)
        if f.endswith(".json")
    ]


def run_prompt(session_id: str, prompt: str) -> str | None:
    """Parse /governor command from prompt. Returns hook JSON or None."""
    # Find /governor command in prompt
    line = None
    for l in prompt.splitlines():
        stripped = l.strip()
        if stripped.startswith("/governor"):
            line = stripped
            break

    if not line:
        return None

    parts = line.split()
    # parts[0] == "/governor"
    if len(parts) < 2:
        return _hook_output("Usage: /governor <machine|off|status|transition|evidence>")

    subcmd = parts[1]

    if subcmd == "off":
        deactivate_governor(session_id)
        return _hook_output("Governor deactivated.")

    if subcmd == "status":
        engine = load_engine(session_id)
        if not engine:
            return _hook_output("Governor is not active.")
        node = engine._get_node()
        edges = [e for e in engine.config.edges if e.from_state == engine.current_phase]
        targets = [e.to_state for e in edges]
        blocked = node.blocked_tools or []
        ctx = (
            f"Phase: {engine.current_phase}. "
            f"Blocked: {', '.join(blocked) if blocked else 'none'}. "
            f"Available transitions: {', '.join(targets) if targets else 'none'}."
        )
        return _hook_output(ctx)

    if subcmd == "transition":
        if len(parts) < 3:
            return _hook_output("Usage: /governor transition <target> [evidence_key]")
        target = parts[2]
        evidence_key = parts[3] if len(parts) > 3 else None
        engine = load_engine(session_id)
        if not engine:
            return _hook_output("Governor is not active.")
        result = engine.want_to_transition(target, evidence_key)
        if result["action"] == "allow":
            node = engine._get_node()
            blocked = node.blocked_tools or []
            ctx = (
                f"Transition allowed: {result['from_state']} -> {result['to_state']}. "
                f"Now in {engine.current_phase}. "
                f"Blocked: {', '.join(blocked) if blocked else 'none'}."
            )
        else:
            ctx = f"Transition denied: {result['message']}"
        return _hook_output(ctx)

    if subcmd == "evidence":
        engine = load_engine(session_id)
        if not engine:
            return _hook_output("Governor is not active.")
        if not engine.locker:
            return _hook_output("No evidence locker configured.")
        keys = engine.locker.keys()
        if not keys:
            return _hook_output("Evidence locker is empty.")
        lines = []
        for key in keys:
            entry = engine.locker.retrieve(key)
            if entry:
                lines.append(
                    f"  {key}: type={entry['type']}, tool={entry['tool_name']}, "
                    f"time={entry['timestamp']}"
                )
        ctx = "Evidence locker:\n" + "\n".join(lines)
        return _hook_output(ctx)

    # Treat as machine name: /governor tdd
    machine_name = subcmd
    machine_path = os.path.join(_MACHINE_DIR, f"{machine_name}.json")
    if not os.path.exists(machine_path):
        available = _available_machines()
        ctx = (
            f"Machine '{machine_name}' not found. "
            f"Available: {', '.join(available) if available else 'none'}."
        )
        return _hook_output(ctx)

    engine = activate_governor(session_id, machine_path)
    node = engine._get_node()
    blocked = node.blocked_tools or []
    ctx = (
        f"Governor activated: machine={engine.config.name}, "
        f"phase={engine.current_phase}. "
        f"Blocked: {', '.join(blocked) if blocked else 'none'}."
    )
    return _hook_output(ctx)


def run(args: list[str]) -> None:
    """CLI entry point for `python3 -m governor_v4 prompt`."""
    session_id = None
    for i, arg in enumerate(args):
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]

    if not session_id:
        print("error: --session required", file=sys.stderr)
        sys.exit(1)

    stdin_data = json.loads(sys.stdin.read())
    prompt = stdin_data.get("prompt", "")
    output = run_prompt(session_id, prompt)
    if output:
        print(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_cli.py::TestCmdPrompt -xvs`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/cmd_prompt.py tests/test_v4_cli.py
git commit -m "feat(v4): add cmd_prompt UserPromptSubmit handler with /governor commands"
```

---

## Task 7: Shell Hook Scripts

**Files:**
- Create: `hooks/guvnah/session-start.sh`
- Create: `hooks/guvnah/pre-tool-use.sh`
- Create: `hooks/guvnah/post-tool-use.sh`
- Create: `hooks/guvnah/user-prompt-submit.sh`
- Test: `tests/test_v4_hooks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_hooks.py
"""Integration tests for guvnah shell hook scripts."""

import json
import os
import subprocess
import sys
import pytest

HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks", "guvnah")
REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestShellHooks:
    def test_session_start_inactive_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "session-start.sh")],
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "nonexistent-test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_pre_tool_use_inactive_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "pre-tool-use.sh")],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "x.py"}}),
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "nonexistent-test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_post_tool_use_inactive_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "post-tool-use.sh")],
            input=json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "pytest"},
                "tool_output": "PASSED",
            }),
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "nonexistent-test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_user_prompt_no_command_exits_0(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "user-prompt-submit.sh")],
            input=json.dumps({"prompt": "just a normal prompt"}),
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_SESSION_ID": "test-session",
                 "PYTHONPATH": REPO_ROOT},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_hooks_are_executable(self):
        for name in ["session-start.sh", "pre-tool-use.sh", "post-tool-use.sh", "user-prompt-submit.sh"]:
            path = os.path.join(HOOKS_DIR, name)
            assert os.access(path, os.X_OK), f"{name} is not executable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_hooks.py -xvs`
Expected: FAIL (scripts don't exist)

- [ ] **Step 3: Create the four shell scripts**

```bash
# hooks/guvnah/session-start.sh
#!/usr/bin/env bash
# SessionStart hook — restore governor state if active.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 init --session "$SESSION"
```

```bash
# hooks/guvnah/pre-tool-use.sh
#!/usr/bin/env bash
# PreToolUse hook — evaluate tool call against governor phase.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 evaluate --session "$SESSION"
```

```bash
# hooks/guvnah/post-tool-use.sh
#!/usr/bin/env bash
# PostToolUse hook — capture tool output as evidence.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 capture --session "$SESSION"
```

```bash
# hooks/guvnah/user-prompt-submit.sh
#!/usr/bin/env bash
# UserPromptSubmit hook — parse /governor commands.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

# Quick check: does stdin contain /governor? Read into var for reuse.
INPUT="$(cat)"
printf '%s' "$INPUT" | grep -q '/governor' || exit 0

printf '%s' "$INPUT" | exec python3 -m governor_v4 prompt --session "$SESSION"
```

Mark all four executable: `chmod +x hooks/guvnah/*.sh`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_hooks.py -xvs`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add hooks/guvnah/ tests/test_v4_hooks.py
git commit -m "feat(v4): add guvnah shell hook scripts"
```

---

## Task 8: Install Script + Deployment

**Files:**
- Create: `hooks/guvnah/install.sh`

- [ ] **Step 1: Write the install script**

```bash
# hooks/guvnah/install.sh
#!/usr/bin/env bash
# Deploy guvnah hooks and machines to ~/.claude/plugins/guvnah/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEST="$HOME/.claude/plugins/guvnah"

echo "Installing guvnah to $DEST ..."

# Hooks
mkdir -p "$DEST/hooks"
for f in session-start.sh pre-tool-use.sh post-tool-use.sh user-prompt-submit.sh; do
    cp "$SCRIPT_DIR/$f" "$DEST/hooks/$f"
    chmod +x "$DEST/hooks/$f"
done

# Machines
mkdir -p "$DEST/machines"
for f in "$REPO_ROOT"/machines/*.json; do
    [ -f "$f" ] && cp "$f" "$DEST/machines/$(basename "$f" | sed 's/_v4//')"
done

echo "Done. Add hook entries to your project's .claude/settings.json:"
echo ""
echo '  "SessionStart": [{"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/session-start.sh"}]}],'
echo '  "PreToolUse":   [..., {"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/pre-tool-use.sh"}]}],'
echo '  "PostToolUse":  [{"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/post-tool-use.sh"}]}],'
echo '  "UserPromptSubmit": [..., {"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/user-prompt-submit.sh"}]}]'
```

- [ ] **Step 2: Make executable and verify**

```bash
chmod +x hooks/guvnah/install.sh
bash hooks/guvnah/install.sh
ls -la ~/.claude/plugins/guvnah/hooks/
ls -la ~/.claude/plugins/guvnah/machines/
```

Expected: 4 hook scripts + tdd.json in machines/

- [ ] **Step 3: Commit**

```bash
git add hooks/guvnah/install.sh
git commit -m "feat(v4): add guvnah install script"
```

---

## Task 9: Full Integration Test — TDD Cycle

**Files:**
- Modify: `tests/test_v4_hooks.py` (add end-to-end test)

- [ ] **Step 1: Write the integration test**

Add to `tests/test_v4_hooks.py`:

```python
class TestFullCycle:
    """End-to-end test: activate → block → capture → transition → verify."""

    def test_tdd_cycle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("governor_v4.cli._STATE_ROOT", str(tmp_path))
        machine_dir = tmp_path / "machines"
        machine_dir.mkdir()
        src = os.path.join(REPO_ROOT, "machines", "tdd_v4.json")
        import shutil
        shutil.copy(src, machine_dir / "tdd.json")
        monkeypatch.setattr("governor_v4.cmd_prompt._MACHINE_DIR", str(machine_dir))

        from governor_v4.cli import load_engine, is_governor_active
        from governor_v4.cmd_prompt import run_prompt
        from governor_v4.cmd_evaluate import run_evaluate
        from governor_v4.cmd_capture import run_capture

        # 1. Activate
        output = run_prompt("s1", "/governor tdd")
        assert "writing_tests" in json.loads(output)["hookSpecificOutput"]["additionalContext"]

        # 2. Block production write
        output = run_evaluate("s1", {"tool_name": "Write", "tool_input": {"file_path": "main.py"}})
        assert output is not None
        assert json.loads(output)["decision"] == "block"

        # 3. Allow test write
        output = run_evaluate("s1", {"tool_name": "Write", "tool_input": {"file_path": "test_foo.py"}})
        assert output is None  # allowed

        # 4. Capture pytest output
        output = run_capture("s1", {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_output": "FAILED 1 test",
            "tool_exit_code": 1,
        })
        assert output is not None
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        key = [w for w in ctx.split() if w.startswith("evt_")][0]

        # 5. Transition to fixing_tests
        output = run_prompt("s1", f"/governor transition fixing_tests {key}")
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        assert "fixing_tests" in ctx

        # 6. Verify production write now allowed
        output = run_evaluate("s1", {"tool_name": "Write", "tool_input": {"file_path": "main.py"}})
        assert output is None  # allowed in fixing_tests

        # 7. Status check
        output = run_prompt("s1", "/governor status")
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        assert "fixing_tests" in ctx

        # 8. Evidence check
        output = run_prompt("s1", "/governor evidence")
        ctx = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        assert key in ctx

        # 9. Deactivate
        output = run_prompt("s1", "/governor off")
        assert not is_governor_active("s1")
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_v4_hooks.py::TestFullCycle -xvs`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_v4_hooks.py
git commit -m "test(v4): add full TDD cycle integration test"
```

---

## Task 10: Verify All Tests Pass

- [ ] **Step 1: Run all v4 tests**

```bash
pytest tests/test_v4_*.py -xvs
```

Expected: all PASS

- [ ] **Step 2: Run full test suite**

```bash
pytest -xvs
```

Expected: all tests pass, no regressions

- [ ] **Step 3: Deploy and verify**

```bash
bash hooks/guvnah/install.sh
ls ~/.claude/plugins/guvnah/hooks/
ls ~/.claude/plugins/guvnah/machines/
```

- [ ] **Step 4: Commit if any cleanup needed**

---

## Verification

After all tasks:

1. `pytest tests/test_v4_*.py -v` — all v4 tests pass
2. `python3 -m governor_v4` — prints usage
3. `ls ~/.claude/plugins/guvnah/hooks/` — 4 shell scripts
4. `ls ~/.claude/plugins/guvnah/machines/` — tdd.json
5. Shell hooks exit 0 cleanly when governor is inactive
