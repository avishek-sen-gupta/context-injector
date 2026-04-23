# Test Anatomist — Extraction Design Spec

## Goal

Extract the test hierarchy analysis code from `context-injector` into a standalone, pip-installable repo called `test-anatomist`. It traces test execution and reveals parent-child abstraction hierarchies across a test suite.

## Package Structure

```
test-anatomist/
├── pyproject.toml
├── src/
│   └── test_anatomist/
│       ├── __init__.py          # re-exports public API
│       ├── tracer.py            # CallTree, trace_context, trace_test, is_project_file
│       ├── parenthood.py        # LineSetStrategy, HierarchyGraph, build_hierarchy
│       └── plugin.py            # pytest plugin with --anatomist flag
└── tests/
    ├── test_tracer.py
    └── test_parenthood.py
```

Uses `src/` layout with Hatchling build backend.

## Modules

### tracer.py

Copied from `context-injector/tracer.py`. Contains:

- `CallTree` — hierarchical data structure recording function calls and line executions
- `trace_context()` — context manager that enables `sys.settrace` and yields a `CallTree`
- `trace_test(test_fn, label=None)` — convenience wrapper that traces a callable and prints the tree
- `is_project_file(filename)` — filters stdlib and site-packages from tracing

No external dependencies beyond stdlib.

### parenthood.py

Copied from `context-injector/parenthood.py`. Contains:

- `ParenthoodStrategy` — Protocol defining the `containment_score` interface
- `LineSetStrategy` — concrete strategy comparing line-set overlap between two `CallTree`s
- `HierarchyGraph` — dataclass bundling the DAG (adjacency dict, all test names, threshold) with `render_text()` and `render_mermaid()` methods. Includes deduplication in text output and a `roots` cached property.
- `build_hierarchy(trees, strategy, threshold=0.95)` — builds a transitively-reduced parent-child DAG from test call trees, returns a `HierarchyGraph`

Depends on `tracer.CallTree` (internal import).

### plugin.py

Pytest plugin, auto-registered via `pytest11` entry point. Behavior:

- **Opt-in**: Only activates when `--anatomist` is passed to pytest. No-op otherwise (zero overhead).
- **Tracing**: Wraps each test in `trace_context()`, collecting a `CallTree` per test node ID.
- **Output**: After the session, builds the hierarchy and prints it.
- **CLI flags**:
  - `--anatomist` — enable tracing and hierarchy output
  - `--anatomist-threshold=FLOAT` — containment threshold (default: 0.95)
  - `--anatomist-format=text|mermaid` — output format (default: text)

### __init__.py

Re-exports the public API for programmatic use:

- `CallTree`, `trace_context`, `trace_test` from `.tracer`
- `LineSetStrategy`, `HierarchyGraph`, `build_hierarchy` from `.parenthood`

## pyproject.toml

```toml
[project]
name = "test-anatomist"
version = "0.1.0"
description = "Trace test execution and reveal parent-child abstraction hierarchies"
requires-python = ">=3.10"
dependencies = ["pytest"]

[project.entry-points.pytest11]
test_anatomist = "test_anatomist.plugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/test_anatomist"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## Installation

During development, install as editable in the consuming repo:

```bash
# pip
pip install -e ../test-anatomist

# uv
uv pip install -e ../test-anatomist

# poetry
poetry add --group dev ../test-anatomist  # with develop = true
```

## Usage

```bash
# Run tests with hierarchy analysis
pytest --anatomist

# Custom threshold
pytest --anatomist --anatomist-threshold=0.85

# Mermaid output
pytest --anatomist --anatomist-format=mermaid
```

## What stays in context-injector

- `trace_experiment.py` — coupled to GovernorV4, serves as a demo/integration script
- `run_parenthood.py` — superseded by the pytest plugin

## What moves to test-anatomist

| Source (context-injector) | Destination (test-anatomist) |
|---|---|
| `tracer.py` | `src/test_anatomist/tracer.py` |
| `parenthood.py` | `src/test_anatomist/parenthood.py` |
| `tests/test_tracer.py` | `tests/test_tracer.py` |
| `tests/test_parenthood.py` | `tests/test_parenthood.py` |
| `run_parenthood.py` (logic) | `src/test_anatomist/plugin.py` (rewritten as proper plugin) |

## Import adjustments

In the new repo, internal imports change from bare module names to package-relative imports:

- `from tracer import CallTree` becomes `from test_anatomist.tracer import CallTree` (or `from .tracer import CallTree` within the package)
- Tests use `from test_anatomist import ...` or `from test_anatomist.tracer import ...`
