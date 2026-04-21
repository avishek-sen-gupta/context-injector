"""Tests for the setup-bash-env SessionStart hook."""

import json
import os
import subprocess

HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks", "guvnah")


class TestSetupBashEnv:
    def test_outputs_environment_json(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "setup-bash-env.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert "environment" in parsed
        assert "BASH_ENV" in parsed["environment"]
        assert parsed["environment"]["BASH_ENV"].endswith("bash-strict.sh")

    def test_bash_env_points_to_existing_file(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "setup-bash-env.sh")],
            capture_output=True, text=True,
        )
        parsed = json.loads(result.stdout)
        assert os.path.isfile(parsed["environment"]["BASH_ENV"])

    def test_bash_strict_enables_pipefail(self):
        strict_path = os.path.join(HOOKS_DIR, "bash-strict.sh")
        with open(strict_path) as f:
            content = f.read()
        assert "set -o pipefail" in content

    def test_hook_is_executable(self):
        path = os.path.join(HOOKS_DIR, "setup-bash-env.sh")
        assert os.access(path, os.X_OK)

    def test_additional_context_mentions_pipefail(self):
        result = subprocess.run(
            ["bash", os.path.join(HOOKS_DIR, "setup-bash-env.sh")],
            capture_output=True, text=True,
        )
        parsed = json.loads(result.stdout)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "pipefail" in ctx.lower()
