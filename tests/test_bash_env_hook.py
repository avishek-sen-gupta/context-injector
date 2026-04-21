"""Tests for the setup-bash-env SessionStart hook."""

import json
import os
import subprocess
import tempfile

HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks", "guvnah")


class TestSetupBashEnv:
    def test_writes_bash_env_to_claude_env_file(self, tmp_path):
        env_file = tmp_path / "claude_env"
        env_file.touch()
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "setup-bash-env.sh")],
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_ENV_FILE": str(env_file)},
        )
        assert result.returncode == 0
        content = env_file.read_text()
        assert "export BASH_ENV=" in content
        assert "bash-strict.sh" in content

    def test_outputs_context_json(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "setup-bash-env.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "pipefail" in ctx.lower()

    def test_no_claude_env_file_still_exits_0(self):
        """Without CLAUDE_ENV_FILE, hook outputs context but doesn't crash."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ENV_FILE"}
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "setup-bash-env.sh")],
            capture_output=True, text=True,
            env=env,
        )
        assert result.returncode == 0

    def test_bash_strict_enables_pipefail(self):
        strict_path = os.path.join(HOOKS_DIR, "bash-strict.sh")
        with open(strict_path) as f:
            content = f.read()
        assert "set -o pipefail" in content

    def test_hook_is_executable(self):
        path = os.path.join(HOOKS_DIR, "setup-bash-env.sh")
        assert os.access(path, os.X_OK)

    def test_bash_env_points_to_existing_file(self, tmp_path):
        env_file = tmp_path / "claude_env"
        env_file.touch()
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "setup-bash-env.sh")],
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_ENV_FILE": str(env_file)},
        )
        content = env_file.read_text()
        # Extract the path from 'export BASH_ENV="..."'
        path = content.split('"')[1]
        assert os.path.isfile(path)
