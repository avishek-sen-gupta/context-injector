# uv Migration Design

## Goal

Replace manual `pip install` dependency management with [uv](https://docs.astral.sh/uv/) for reproducible, fast installs and a proper lockfile.

## Current State

- `pyproject.toml` declares `python-statemachine>=3.0.0` (runtime) and `pytest>=8.0` (dev)
- `tinydb>=4.0.0` and `beniget>=0.5.0` are runtime deps but only documented in `install-governor.sh`, not in `pyproject.toml`
- CI (`ci.yml`) manually `pip install`s each dep without using `pyproject.toml`
- `semgrep` and `ast-grep` are external CLI tools, not Python library deps

## Design

### Dependencies in `pyproject.toml`

Runtime dependencies (project.dependencies):
- `python-statemachine>=3.0.0` (already present)
- `tinydb>=4.0.0` (add)
- `beniget>=0.5.0` (add)

Dev dependencies (project.optional-dependencies.dev):
- `pytest>=8.0` (already present)

External tools (not in pyproject.toml):
- `semgrep` — installed via `uv tool install semgrep` in CI, `pip install semgrep` locally
- `ast-grep` (`sg`) — installed via npm/cargo, optional

### New Files

- `uv.lock` — Generated lockfile, committed for reproducibility
- `.python-version` — Pins Python 3.13, created by uv

### CI Workflow (`ci.yml`)

Replace `actions/setup-python` + manual pip install with:

```yaml
- uses: astral-sh/setup-uv@v6
- run: uv sync --dev
- run: uv tool install semgrep
- run: uv run pytest tests/ -v
```

### README

Update dependencies and installation sections to reference `uv sync` for development setup.

### No Changes

- All Python source code, tests, gates, hooks, lint rules
- `install-governor.sh` (runtime checks for installed binaries, independent of dev tooling)
- `pyproject.toml` structure (uv uses the same PEP 621 format)

## Out of Scope

- Moving to `uv` workspaces (single-package project, not needed)
- Adding semgrep/ast-grep as Python deps (they are external CLI tools)
- Changing `install-governor.sh` (it checks system-level binaries, not the dev environment)
