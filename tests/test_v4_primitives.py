import pytest
from governor_v4.primitives import check_tool_allowed, match_capture_rule


class TestCheckToolAllowed:
    def test_no_blocklist_allows(self):
        assert check_tool_allowed("Edit", "/test.py", blocked=None, exceptions=None)

    def test_empty_blocklist_allows(self):
        assert check_tool_allowed("Bash", "ls", blocked=[], exceptions=None)

    def test_exact_name_blocks(self):
        assert not check_tool_allowed(
            "Write", "/main.py", blocked=["Write", "Edit"], exceptions=None
        )

    def test_exception_overrides_block(self):
        assert check_tool_allowed(
            "Write", "test_foo.py", blocked=["Write"], exceptions=["Write(test_*)"]
        )

    def test_non_matching_exception_stays_blocked(self):
        assert not check_tool_allowed(
            "Write", "main.py", blocked=["Write"], exceptions=["Write(test_*)"]
        )

    def test_non_blocked_tool_allowed(self):
        assert check_tool_allowed(
            "Read", "/test.py", blocked=["Write", "Edit"], exceptions=None
        )

    def test_edit_exception_with_path(self):
        assert check_tool_allowed(
            "Edit", "test_bar.py", blocked=["Edit"], exceptions=["Edit(test_*)"]
        )

    def test_edit_blocked_without_matching_exception(self):
        assert not check_tool_allowed(
            "Edit", "src/auth.py", blocked=["Edit"], exceptions=["Edit(test_*)"]
        )

    def test_exception_matches_absolute_path(self):
        assert check_tool_allowed(
            "Write",
            "/Users/dev/project/test_foo.py",
            blocked=["Write"],
            exceptions=["Write(test_*)"],
        )

    def test_exception_matches_absolute_path_edit(self):
        assert check_tool_allowed(
            "Edit",
            "/home/user/code/test_bar.py",
            blocked=["Edit"],
            exceptions=["Edit(test_*)"],
        )

    def test_absolute_path_non_test_stays_blocked(self):
        assert not check_tool_allowed(
            "Write",
            "/Users/dev/project/src/main.py",
            blocked=["Write"],
            exceptions=["Write(test_*)"],
        )

    def test_absolute_path_nested_test_file(self):
        assert check_tool_allowed(
            "Write",
            "/Users/dev/project/tests/test_auth.py",
            blocked=["Write"],
            exceptions=["Write(test_*)"],
        )


class TestMatchCaptureRule:
    def test_bash_pytest_matches(self):
        assert match_capture_rule("Bash", "pytest tests/", "Bash(*pytest*)")

    def test_bash_pytest_verbose_matches(self):
        assert match_capture_rule("Bash", "pytest tests/ -xvs", "Bash(*pytest*)")

    def test_bash_non_pytest_no_match(self):
        assert not match_capture_rule("Bash", "ls -la", "Bash(*pytest*)")

    def test_wrong_tool_no_match(self):
        assert not match_capture_rule("Write", "test_foo.py", "Bash(*pytest*)")

    def test_bash_ruff_matches(self):
        assert match_capture_rule("Bash", "ruff check src/", "Bash(*ruff*)")

    def test_bare_tool_pattern(self):
        assert match_capture_rule("Bash", "anything", "Bash")

    def test_bare_tool_pattern_no_match(self):
        assert not match_capture_rule("Write", "test.py", "Bash")
