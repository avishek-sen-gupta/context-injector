# tests/test_lint_gate.py
"""Tests for the LintGate — ast-grep based lint checking on transition boundaries."""

import os
import shutil
import pytest

from gates.base import GateContext, GateVerdict
from gates.lint import LintGate


def _make_file(tmp_path, filename, content):
    """Write a Python file and return its path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _make_context(tmp_path, files, rules_dir=None):
    """Build a GateContext with the given recent_files."""
    return GateContext(
        state_name="fixing_tests",
        transition_name="pytest_pass",
        recent_tools=[f"Write({f})" for f in files],
        recent_files=files,
        machine=None,
        project_root=str(tmp_path),
    )


@pytest.fixture
def rules_dir(tmp_path):
    """Create a minimal rules directory with one rule."""
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "no-bare-except.yml").write_text(
        'id: no-bare-except\nlanguage: python\nrule:\n  pattern: |\n'
        '    try:\n      $$$BODY\n    except:\n      $$$HANDLER\n'
        'message: "Bare except"\nseverity: warning\n'
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


@pytest.fixture
def multi_rules_dir(tmp_path):
    """Create a rules directory with multiple rules."""
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "no-bare-except.yml").write_text(
        'id: no-bare-except\nlanguage: python\nrule:\n  pattern: |\n'
        '    try:\n      $$$BODY\n    except:\n      $$$HANDLER\n'
        'message: "Bare except"\nseverity: warning\n'
    )
    (rules / "no-print.yml").write_text(
        'id: no-print\nlanguage: python\nrule:\n  pattern: print($$$ARGS)\n'
        'message: "print() — use logging"\nseverity: warning\n'
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


@pytest.fixture
def mutation_rules_dir(tmp_path):
    """Create a rules directory with subscript mutation rules."""
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "no-subscript-mutation.yml").write_text(
        'id: no-subscript-mutation\nlanguage: python\nrule:\n'
        '  pattern: $OBJ[$KEY] = $VAL\n'
        'message: "Subscript mutation"\nseverity: warning\n'
    )
    (rules / "no-subscript-augmented-mutation.yml").write_text(
        'id: no-subscript-augmented-mutation\nlanguage: python\nrule:\n'
        '  any:\n'
        '    - pattern: $OBJ[$KEY] += $VAL\n'
        '    - pattern: $OBJ[$KEY] -= $VAL\n'
        '    - pattern: $OBJ[$KEY] *= $VAL\n'
        'message: "Subscript augmented mutation"\nseverity: warning\n'
    )
    (rules / "no-subscript-del.yml").write_text(
        'id: no-subscript-del\nlanguage: python\nrule:\n'
        '  pattern: del $OBJ[$KEY]\n'
        'message: "Subscript deletion"\nseverity: warning\n'
    )
    (rules / "no-subscript-tuple-mutation.yml").write_text(
        'id: no-subscript-tuple-mutation\nlanguage: python\nrule:\n'
        '  any:\n'
        '    - pattern: $OBJ[$KEY], $$$REST = $$$VALS\n'
        '    - pattern: $$$REST, $OBJ[$KEY] = $$$VALS\n'
        'message: "Tuple subscript mutation"\nseverity: warning\n'
    )
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


needs_sg = pytest.mark.skipif(
    shutil.which("sg") is None and shutil.which("ast-grep") is None,
    reason="ast-grep (sg) not installed",
)


class TestResolveRulesDir:
    """Tests for rules directory resolution logic."""

    def test_explicit_rules_dir_takes_priority(self, tmp_path):
        gate = LintGate(rules_dir="/explicit/path")
        assert gate._resolve_rules_dir(str(tmp_path)) == "/explicit/path"

    def test_project_local_rules_found(self, tmp_path):
        lint_dir = tmp_path / "scripts" / "lint"
        lint_dir.mkdir(parents=True)
        (lint_dir / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        gate = LintGate()
        assert gate._resolve_rules_dir(str(tmp_path)) == str(lint_dir)

    def test_falls_back_to_config_file(self, tmp_path, monkeypatch):
        """When project has no scripts/lint/, falls back to config.json."""
        config_lint = tmp_path / "installed" / "scripts" / "lint"
        config_lint.mkdir(parents=True)
        (config_lint / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        # Write config.json next to the gates/ package (parent of __file__)
        gates_dir = os.path.dirname(os.path.abspath(LintGate.__module__.replace(".", "/") + ".py"))
        config_path = os.path.join(os.path.dirname(gates_dir), "config.json")
        monkeypatch.setattr(
            LintGate, "_read_config_rules_dir",
            staticmethod(lambda: str(config_lint)),
        )
        gate = LintGate()
        empty_project = tmp_path / "empty_project"
        empty_project.mkdir()
        result = gate._resolve_rules_dir(str(empty_project))
        assert result == str(config_lint)

    def test_project_local_takes_priority_over_config(self, tmp_path, monkeypatch):
        """Project-local scripts/lint/ wins over config.json."""
        project_lint = tmp_path / "scripts" / "lint"
        project_lint.mkdir(parents=True)
        (project_lint / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        config_lint = tmp_path / "installed" / "scripts" / "lint"
        config_lint.mkdir(parents=True)
        (config_lint / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
        monkeypatch.setattr(
            LintGate, "_read_config_rules_dir",
            staticmethod(lambda: str(config_lint)),
        )
        gate = LintGate()
        result = gate._resolve_rules_dir(str(tmp_path))
        assert result == str(project_lint)

    def test_returns_none_when_no_rules_found(self, tmp_path, monkeypatch):
        """When neither project nor config has rules, returns None."""
        monkeypatch.setattr(
            LintGate, "_read_config_rules_dir",
            staticmethod(lambda: None),
        )
        gate = LintGate()
        assert gate._resolve_rules_dir(str(tmp_path)) is None

    def test_read_config_rules_dir_parses_json(self, tmp_path, monkeypatch):
        """_read_config_rules_dir reads lint_rules_dir from config.json."""
        # Point __file__ resolution to tmp_path/gates/lint.py
        config = tmp_path / "config.json"
        config.write_text('{"lint_rules_dir": "/some/path"}')
        gates_dir = tmp_path / "gates"
        gates_dir.mkdir()
        monkeypatch.setattr(
            "gates.lint.os.path.abspath",
            lambda p: str(gates_dir / "lint.py") if "lint" in p else os.path.abspath(p),
        )
        # Simpler: just test the method directly with a real config
        import gates.lint as lint_mod
        orig_file = lint_mod.__file__
        # Create config.json at the expected location relative to gates/
        parent = os.path.dirname(os.path.dirname(os.path.abspath(orig_file)))
        config_path = os.path.join(parent, "config.json")
        existed = os.path.exists(config_path)
        try:
            with open(config_path, "w") as f:
                f.write('{"lint_rules_dir": "/test/rules/path"}')
            result = LintGate._read_config_rules_dir()
            assert result == "/test/rules/path"
        finally:
            if not existed:
                os.remove(config_path)

    def test_read_config_returns_none_when_missing(self, tmp_path, monkeypatch):
        """_read_config_rules_dir returns None when config.json doesn't exist."""
        # Point to a nonexistent parent
        fake_gates = tmp_path / "nonexistent" / "gates"
        monkeypatch.setattr(
            "gates.lint.os.path.abspath",
            lambda p: str(fake_gates / "lint.py"),
        )
        result = LintGate._read_config_rules_dir()
        assert result is None


class TestLintGateWithoutSg:
    """Tests that work without ast-grep installed."""

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

    def test_passes_when_sg_not_found(self, tmp_path, rules_dir, monkeypatch):
        """If ast-grep is not installed, gate should pass (not block)."""
        path = _make_file(tmp_path, "widget.py", "try:\n    pass\nexcept:\n    pass\n")
        ctx = _make_context(str(tmp_path), [path])
        monkeypatch.setattr(shutil, "which", lambda _: None)
        gate = LintGate(rules_dir=rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

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


@needs_sg
class TestLintGateWithSg:
    """Tests that require ast-grep installed."""

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
        """Untouched files with violations should not cause failure."""
        dirty = _make_file(tmp_path, "dirty.py",
            "try:\n    x = 1\nexcept:\n    pass\n")
        clean = _make_file(tmp_path, "clean.py", "x = 1\n")
        # Only clean.py is in recent_files
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
        """Same file touched multiple times should only be scanned once."""
        path = _make_file(tmp_path, "widget.py", "x = 1\n")
        ctx = _make_context(str(tmp_path), [path, path, path])
        gate = LintGate(rules_dir=rules_dir)
        filtered = gate._filter_python_files(ctx.recent_files)
        assert len(filtered) == 1

    def test_augmented_subscript_mutation_fails(self, tmp_path, mutation_rules_dir):
        """d[key] += amount should be caught."""
        path = _make_file(tmp_path, "widget.py",
            "def increment(d, key, amount=1):\n    d[key] += amount\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-subscript-augmented-mutation" in i for i in result.issues)

    def test_subscript_del_fails(self, tmp_path, mutation_rules_dir):
        """del d[k] should be caught."""
        path = _make_file(tmp_path, "widget.py",
            "def remove(d, k):\n    del d[k]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-subscript-del" in i for i in result.issues)

    def test_tuple_subscript_mutation_fails(self, tmp_path, mutation_rules_dir):
        """d[k1], d[k2] = d[k2], d[k1] should be caught."""
        path = _make_file(tmp_path, "widget.py",
            "def swap(d, k1, k2):\n    d[k1], d[k2] = d[k2], d[k1]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-subscript-tuple-mutation" in i for i in result.issues)

    def test_all_dict_mutations_caught(self, tmp_path, mutation_rules_dir):
        """The exact code from test_dict.py should trigger violations."""
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


@pytest.fixture
def nesting_rules_dir(tmp_path):
    """Create a rules directory with the no-deep-nesting rule."""
    rules = tmp_path / "rules"
    rules.mkdir()
    import shutil as _shutil
    src = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "scripts", "lint", "rules", "no-deep-nesting.yml")
    _shutil.copy(src, rules / "no-deep-nesting.yml")
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


@pytest.fixture
def loop_mutation_rules_dir(tmp_path):
    """Create a rules directory with the no-loop-mutation rule."""
    rules = tmp_path / "rules"
    rules.mkdir()
    import shutil as _shutil
    src = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "scripts", "lint", "rules", "no-loop-mutation.yml")
    _shutil.copy(src, rules / "no-loop-mutation.yml")
    sgconfig = tmp_path / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n")
    return str(tmp_path)


@needs_sg
class TestDeepNestingRule:
    """Tests for the no-deep-nesting ast-grep rule."""

    def test_for_in_for_fails(self, tmp_path, nesting_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(matrix):\n"
            "    for row in matrix:\n"
            "        for cell in row:\n"
            "            process(cell)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-deep-nesting" in i for i in result.issues)

    def test_if_in_for_fails(self, tmp_path, nesting_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items):\n"
            "    for x in items:\n"
            "        if x > 0:\n"
            "            process(x)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-deep-nesting" in i for i in result.issues)

    def test_for_in_if_fails(self, tmp_path, nesting_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items, flag):\n"
            "    if flag:\n"
            "        for x in items:\n"
            "            process(x)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-deep-nesting" in i for i in result.issues)

    def test_if_in_if_fails(self, tmp_path, nesting_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(x, y):\n"
            "    if x > 0:\n"
            "        if y > 0:\n"
            "            process(x, y)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-deep-nesting" in i for i in result.issues)

    def test_triple_nesting_fails(self, tmp_path, nesting_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(cube):\n"
            "    for plane in cube:\n"
            "        for row in plane:\n"
            "            for cell in row:\n"
            "                process(cell)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_flat_for_passes(self, tmp_path, nesting_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items):\n"
            "    for x in items:\n"
            "        process(x)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_flat_if_passes(self, tmp_path, nesting_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(x):\n"
            "    if x > 0:\n"
            "        return x\n"
            "    return 0\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_for_in_nested_function_passes(self, tmp_path, nesting_rules_dir):
        """A for inside a nested function def is not real nesting."""
        path = _make_file(tmp_path, "widget.py",
            "def outer(items):\n"
            "    for x in items:\n"
            "        def inner(ys):\n"
            "            for y in ys:\n"
            "                process(y)\n"
            "        inner(x)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=nesting_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS


@needs_sg
class TestLoopMutationRule:
    """Tests for the no-loop-mutation ast-grep rule."""

    def test_append_in_for_fails(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items):\n"
            "    result = []\n"
            "    for x in items:\n"
            "        result.append(x)\n"
            "    return result\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no-loop-mutation" in i for i in result.issues)

    def test_extend_in_for_fails(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(lists):\n"
            "    result = []\n"
            "    for lst in lists:\n"
            "        result.extend(lst)\n"
            "    return result\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_subscript_assign_in_for_fails(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(d, keys, val):\n"
            "    for k in keys:\n"
            "        d[k] = val\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_augmented_assign_in_for_fails(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items):\n"
            "    total = 0\n"
            "    for x in items:\n"
            "        total += x\n"
            "    return total\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_del_subscript_in_for_fails(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(d, keys):\n"
            "    for k in keys:\n"
            "        del d[k]\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_set_add_in_for_fails(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items):\n"
            "    seen = set()\n"
            "    for x in items:\n"
            "        seen.add(x)\n"
            "    return seen\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_no_mutation_in_for_passes(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items):\n"
            "    for x in items:\n"
            "        print(x)\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_mutation_outside_for_passes(self, tmp_path, loop_mutation_rules_dir):
        path = _make_file(tmp_path, "widget.py",
            "def f(items):\n"
            "    result = []\n"
            "    result.append(42)\n"
            "    return result\n")
        ctx = _make_context(str(tmp_path), [path])
        gate = LintGate(rules_dir=loop_mutation_rules_dir)
        result = gate.evaluate(ctx)
        assert result.verdict == GateVerdict.PASS
