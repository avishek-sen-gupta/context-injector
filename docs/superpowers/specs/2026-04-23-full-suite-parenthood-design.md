# Full Test Suite Parenthood Analysis

## Problem

The parenthood detection system (`parenthood.py`) works but only traces tests listed manually in `trace_experiment.py`. We want to run the analysis across the full test suite (~170 tests) without maintaining a hardcoded list.

## Approach

A standalone script `run_parenthood.py` that calls `pytest.main()` with a custom plugin. Pytest handles all test discovery, fixture resolution, and execution. The plugin wraps each test with `sys.settrace` to collect a `CallTree`, then runs `build_abstraction_tree` and prints the hierarchy after all tests complete.

## Architecture

### trace_context (tracer.py refactor)

Extract the settrace/closure logic from `trace_test()` into a context manager so both `trace_test()` and the pytest plugin can reuse it.

```python
@contextmanager
def trace_context():
    """Yield a CallTree that records execution while the context is active."""
    tree = CallTree()
    def tracer(frame, event, arg):
        if threading.current_thread() is not threading.main_thread():
            return None
        filename = frame.f_code.co_filename
        if not is_project_file(filename):
            return None
        if event == "call":
            tree.push_call(filename, frame.f_code.co_name, frame.f_lineno)
            return tracer
        elif event == "line":
            tree.add_line(filename, frame.f_lineno)
        elif event == "return":
            tree.pop_call()
        return tracer
    sys.settrace(tracer)
    try:
        yield tree
    finally:
        sys.settrace(None)
```

`trace_test()` is rewritten to use `trace_context()` internally. Its public API and behavior are unchanged.

### ParenthoodPlugin (run_parenthood.py)

A pytest plugin class with two hooks:

- **`pytest_runtest_call(item)`** — Wraps `item.runtest()` with `trace_context()`. Stores the resulting `CallTree` keyed by `item.nodeid`.
- **`pytest_sessionfinish(session)`** — Runs `build_abstraction_tree()` on all collected trees using `LineSetStrategy`, prints the hierarchy via `render_hierarchy()`.

### Entry point

```python
if __name__ == "__main__":
    plugin = ParenthoodPlugin()
    pytest.main(["tests/", "-q"], plugins=[plugin])
```

## File layout

| File | Role |
|---|---|
| `tracer.py` | **Modify.** Add `trace_context()` context manager. Rewrite `trace_test()` to use it. |
| `run_parenthood.py` | **Create.** Standalone script with `ParenthoodPlugin` class. |
| `parenthood.py` | **Unchanged.** |
| `trace_experiment.py` | **Unchanged.** |

## Scope

- No CLI flags — run as `python3 run_parenthood.py`.
- No persistence — results printed to stdout.
- No changes to existing `parenthood.py` or its tests.
- `trace_experiment.py` continues to work as before.

## Testing

- Unit test `trace_context()`: verify it yields a CallTree that records lines during execution.
- Unit test that `trace_test()` still works after the refactor (existing tests cover this implicitly via `test_parenthood.py`).
- Run `run_parenthood.py` end-to-end and verify it traces all tests and prints a hierarchy.
