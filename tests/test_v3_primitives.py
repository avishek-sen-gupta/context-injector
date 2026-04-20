import pytest
from governor_v3.primitives import check_tool_allowed, GATE_REGISTRY

class TestCheckToolAllowed:
    def test_no_blocklist_allows(self):
        assert check_tool_allowed("Edit", "/test.py", blocked=None, exceptions=None)

    def test_empty_blocklist_allows(self):
        assert check_tool_allowed("Bash", "ls", blocked=[], exceptions=None)

    def test_exact_name_blocks(self):
        assert not check_tool_allowed("Write", "/main.py", blocked=["Write", "Edit"], exceptions=None)

    def test_exception_overrides_block(self):
        assert check_tool_allowed("Write", "test_foo.py", blocked=["Write"], exceptions=["Write(test_*)"])

    def test_non_matching_exception_stays_blocked(self):
        assert not check_tool_allowed("Write", "main.py", blocked=["Write"], exceptions=["Write(test_*)"])

    def test_non_blocked_tool_allowed(self):
        assert check_tool_allowed("Read", "/test.py", blocked=["Write", "Edit"], exceptions=None)

    def test_bash_not_blocked_by_write_block(self):
        assert check_tool_allowed("Bash", "pytest", blocked=["Write", "Edit"], exceptions=None)

    def test_edit_exception_with_path(self):
        assert check_tool_allowed("Edit", "test_bar.py", blocked=["Edit"], exceptions=["Edit(test_*)"])

    def test_edit_blocked_without_matching_exception(self):
        assert not check_tool_allowed("Edit", "src/auth.py", blocked=["Edit"], exceptions=["Edit(test_*)"])

class TestGateRegistry:
    def test_registry_has_lint(self):
        assert "lint" in GATE_REGISTRY

    def test_registry_has_reassignment(self):
        assert "reassignment" in GATE_REGISTRY

    def test_registry_has_test_quality(self):
        assert "test_quality" in GATE_REGISTRY
