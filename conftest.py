# conftest.py — project-root pytest configuration
import os
import sys

# Make python-fp-lint submodule importable
_lint_pkg = os.path.join(os.path.dirname(__file__), "scripts", "lint")
if _lint_pkg not in sys.path:
    sys.path.insert(0, _lint_pkg)
