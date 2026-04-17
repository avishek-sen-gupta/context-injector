"""Integration tests for gates/terminology shell scripts.

Each test invokes the scripts via subprocess with HOME overridden to a temp
directory, isolating the real ~/.config/git/blocklist.txt from test state.
"""

import os
import subprocess
from pathlib import Path

import pytest

# ── Script paths ────────────────────────────────────────────────────────────

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_GATE_DIR = os.path.join(_REPO_ROOT, "gates", "terminology")
CHECK_SCRIPT = os.path.join(_GATE_DIR, "check-terminology")
SCAN_SCRIPT = os.path.join(_GATE_DIR, "scan-history")
INSTALL_SCRIPT = os.path.join(_REPO_ROOT, "install-terminology-guard.sh")
UNINSTALL_SCRIPT = os.path.join(_REPO_ROOT, "uninstall-terminology-guard.sh")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_home(tmp_path):
    """Isolated HOME directory so blocklist never touches ~/.config/git/."""
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Minimal git repo with one initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--template="], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, capture_output=True)
    (repo / ".git" / "hooks").mkdir(exist_ok=True)
    _commit(repo, "README.md", "hello\n")
    return repo


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_blocklist(home_dir, patterns):
    config_dir = Path(home_dir) / ".config" / "git"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "blocklist.txt").write_text("\n".join(patterns) + "\n")


def _make_excludelist(home_dir, globs):
    config_dir = Path(home_dir) / ".config" / "git"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "blocklist-exclude.txt").write_text("\n".join(globs) + "\n")


def _stage(repo, filename, content):
    (Path(repo) / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=repo, check=True, capture_output=True)


def _commit(repo, filename, content, message="init"):
    _stage(repo, filename, content)
    subprocess.run(
        ["git", "commit", "-m", message, "--no-verify"],
        cwd=repo, check=True, capture_output=True,
    )


def _run(script, cwd, home):
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", script],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def _install(cwd, home):
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["sh", INSTALL_SCRIPT],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def _uninstall(cwd, home):
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["sh", UNINSTALL_SCRIPT],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


# ── check-terminology tests ──────────────────────────────────────────────────


class TestCheckTerminology:
    def test_no_blocklist_exits_cleanly(self, tmp_git_repo, tmp_home):
        _stage(tmp_git_repo, "file.py", "some content\n")
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 0

    def test_empty_blocklist_exits_cleanly(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, [])
        _stage(tmp_git_repo, "file.py", "some content\n")
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 0

    def test_no_staged_changes_exits_cleanly(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["forbidden"])
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 0

    def test_clean_staged_change_exits_cleanly(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["forbidden"])
        _stage(tmp_git_repo, "file.py", "safe content\n")
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 0

    def test_staged_forbidden_term_blocked(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["forbidden"])
        _stage(tmp_git_repo, "file.py", "contains forbidden word\n")
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 1

    def test_deleted_lines_not_flagged(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["badterm"])
        _commit(tmp_git_repo, "file.py", "line with badterm\n", message="add badterm")
        # Stage a deletion of the file
        subprocess.run(["git", "rm", "file.py"], cwd=tmp_git_repo, check=True, capture_output=True)
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 0

    def test_comment_lines_in_blocklist_ignored(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["# this is a comment", "forbidden"])
        _stage(tmp_git_repo, "file.py", "contains forbidden\n")
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 1

    def test_output_contains_staged_label_on_violation(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["acme"])
        _stage(tmp_git_repo, "file.py", "acme corp reference\n")
        result = _run(CHECK_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 1
        assert "staged" in result.stdout


# ── scan-history tests ───────────────────────────────────────────────────────


class TestScanHistory:
    def test_no_blocklist_exits_cleanly(self, tmp_git_repo, tmp_home):
        result = _run(SCAN_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 0

    def test_clean_history_exits_cleanly(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["acme"])
        _commit(tmp_git_repo, "clean.py", "nothing here\n", message="clean commit")
        result = _run(SCAN_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 0
        assert "No forbidden terms found" in result.stdout

    def test_file_content_violation_detected(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["acme"])
        _commit(tmp_git_repo, "secret.py", "acme project data\n", message="add file")
        result = _run(SCAN_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 1

    def test_commit_message_violation_detected(self, tmp_git_repo, tmp_home):
        _make_blocklist(tmp_home, ["acme"])
        # Commit message contains the forbidden term; file content is clean
        _commit(tmp_git_repo, "clean.py", "nothing bad here\n", message="acme integration work")
        result = _run(SCAN_SCRIPT, tmp_git_repo, tmp_home)
        assert result.returncode == 1


# ── installer tests ──────────────────────────────────────────────────────────


class TestInstaller:
    def test_install_fails_outside_git_repo(self, tmp_path, tmp_home):
        non_git = tmp_path / "not-a-repo"
        non_git.mkdir()
        result = _install(non_git, tmp_home)
        assert result.returncode != 0
        assert "not a git repository" in result.stderr

    def test_install_creates_scripts_in_install_dir(self, tmp_git_repo, tmp_home):
        result = _install(tmp_git_repo, tmp_home)
        assert result.returncode == 0
        install_dir = Path(tmp_home) / ".claude" / "plugins" / "context-injector" / "gates" / "terminology"
        assert (install_dir / "check-terminology").exists()
        assert (install_dir / "scan-history").exists()
        assert (install_dir / "lib-terminology.sh").exists()

    def test_install_creates_pre_commit_hook(self, tmp_git_repo, tmp_home):
        result = _install(tmp_git_repo, tmp_home)
        assert result.returncode == 0
        hook = tmp_git_repo / ".git" / "hooks" / "pre-commit"
        assert hook.exists()
        assert "check-terminology" in hook.read_text()

    def test_install_is_idempotent(self, tmp_git_repo, tmp_home):
        _install(tmp_git_repo, tmp_home)
        _install(tmp_git_repo, tmp_home)
        hook = tmp_git_repo / ".git" / "hooks" / "pre-commit"
        content = hook.read_text()
        assert content.count("check-terminology") == 1

    def test_install_appends_to_existing_hook(self, tmp_git_repo, tmp_home):
        hook_path = tmp_git_repo / ".git" / "hooks" / "pre-commit"
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text("#!/bin/sh\necho existing-hook\n")
        hook_path.chmod(0o755)

        result = _install(tmp_git_repo, tmp_home)
        assert result.returncode == 0
        content = hook_path.read_text()
        assert "existing-hook" in content
        assert "check-terminology" in content


# ── uninstaller tests ────────────────────────────────────────────────────────


class TestUninstaller:
    def test_uninstall_fails_outside_git_repo(self, tmp_path, tmp_home):
        non_git = tmp_path / "not-a-repo"
        non_git.mkdir()
        result = _uninstall(non_git, tmp_home)
        assert result.returncode != 0
        assert "not a git repository" in result.stderr

    def test_uninstall_removes_guard_from_hook(self, tmp_git_repo, tmp_home):
        _install(tmp_git_repo, tmp_home)
        _uninstall(tmp_git_repo, tmp_home)
        hook = tmp_git_repo / ".git" / "hooks" / "pre-commit"
        if hook.exists():
            assert "check-terminology" not in hook.read_text()

    def test_uninstall_deletes_empty_hook(self, tmp_git_repo, tmp_home):
        # Install creates a hook that only contains the terminology guard
        _install(tmp_git_repo, tmp_home)
        _uninstall(tmp_git_repo, tmp_home)
        hook = tmp_git_repo / ".git" / "hooks" / "pre-commit"
        assert not hook.exists()

    def test_uninstall_with_no_hook_is_graceful(self, tmp_git_repo, tmp_home):
        result = _uninstall(tmp_git_repo, tmp_home)
        assert result.returncode == 0

    def test_uninstall_removes_scripts(self, tmp_git_repo, tmp_home):
        _install(tmp_git_repo, tmp_home)
        _uninstall(tmp_git_repo, tmp_home)
        install_dir = Path(tmp_home) / ".claude" / "plugins" / "context-injector" / "gates" / "terminology"
        assert not (install_dir / "check-terminology").exists()
        assert not (install_dir / "scan-history").exists()
        assert not (install_dir / "lib-terminology.sh").exists()
