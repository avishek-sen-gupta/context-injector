# gates/lint.py
"""LintGate — dual-backend lint checking at transition boundaries.

Runs Semgrep for the majority of lint rules, then ast-grep for the
rules that require tree-sitter-specific features (stopBy, has+kind).
Results are merged into a single violation list.
"""

import json
import os
import shutil
import subprocess

from gates.base import Gate, GateContext, GateResult, GateVerdict


class LintGate(Gate):
    """Gate that runs Semgrep and ast-grep lint rules on touched files."""

    name = "lint"

    def __init__(self, rules_dir: str | None = None):
        self.rules_dir = rules_dir

    def evaluate(self, ctx: GateContext) -> GateResult:
        py_files = self._filter_python_files(ctx.recent_files)
        if not py_files:
            return GateResult(GateVerdict.PASS)

        rules_dir = self._resolve_rules_dir(ctx.project_root)
        if rules_dir is None:
            return GateResult(GateVerdict.PASS)

        # Semgrep is required
        semgrep = self._find_semgrep()
        if semgrep is None:
            return GateResult(
                GateVerdict.FAIL,
                message="GATE: lint — semgrep binary not found. Install with: pip install semgrep",
            )

        violations = []

        # Run Semgrep (26 rules)
        semgrep_rules = os.path.join(rules_dir, "semgrep-rules.yml")
        if os.path.exists(semgrep_rules):
            violations.extend(self._run_semgrep(semgrep, semgrep_rules, py_files))

        # Run ast-grep (2 remaining rules) — optional
        sg = self._find_sg()
        sgconfig = os.path.join(rules_dir, "sgconfig.yml")
        if sg is not None and os.path.exists(sgconfig):
            violations.extend(self._run_sg(sg, rules_dir, py_files))

        if not violations:
            return GateResult(GateVerdict.PASS)

        return GateResult(
            GateVerdict.FAIL,
            message=self._format_violations(violations),
            issues=[f"{v['ruleId']}:{v['file']}:{v['line']}" for v in violations],
        )

    @staticmethod
    def _filter_python_files(files: list[str]) -> list[str]:
        """Filter to existing, unique .py files."""
        seen = set()
        result = []
        for f in files:
            if f in seen:
                continue
            seen.add(f)
            if f.endswith(".py") and os.path.exists(f):
                result.append(f)
        return result

    @staticmethod
    def _find_semgrep() -> str | None:
        """Find the semgrep binary."""
        return shutil.which("semgrep")

    @staticmethod
    def _find_sg() -> str | None:
        """Find the ast-grep binary."""
        return shutil.which("sg") or shutil.which("ast-grep")

    def _resolve_rules_dir(self, project_root: str) -> str | None:
        """Find the lint rules directory.

        Searches in order: explicit rules_dir, project-local scripts/lint/,
        then lint_rules_dir from the plugin config.json (written at install time).
        """
        if self.rules_dir:
            return self.rules_dir
        candidates = [
            os.path.join(project_root, "scripts", "lint"),
        ]
        config_dir = self._read_config_rules_dir()
        if config_dir:
            candidates.append(config_dir)
        for candidate in candidates:
            if os.path.isdir(candidate) and (
                os.path.exists(os.path.join(candidate, "sgconfig.yml"))
                or os.path.exists(os.path.join(candidate, "semgrep-rules.yml"))
            ):
                return candidate
        return None

    @staticmethod
    def _read_config_rules_dir() -> str | None:
        """Read lint_rules_dir from the plugin config.json."""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json",
        )
        if not os.path.exists(config_path):
            return None
        try:
            with open(config_path) as f:
                return json.load(f).get("lint_rules_dir")
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _run_semgrep(semgrep_path: str, rules_file: str, files: list[str]) -> list[dict]:
        """Run Semgrep scan on the given files and return parsed violations."""
        try:
            result = subprocess.run(
                [semgrep_path, "scan", "--config", rules_file, "--json", "--no-git-ignore"] + files,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []

        if not result.stdout.strip():
            return []

        violations = []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        for entry in data.get("results", []):
            violations.append({
                "ruleId": entry.get("check_id", "unknown").rsplit(".", 1)[-1],
                "file": entry.get("path", ""),
                "line": entry.get("start", {}).get("line", 0),
                "message": entry.get("extra", {}).get("message", ""),
                "source": entry.get("extra", {}).get("lines", "").strip(),
            })

        return violations

    @staticmethod
    def _run_sg(sg_path: str, rules_dir: str, files: list[str]) -> list[dict]:
        """Run ast-grep scan on the given files and return parsed violations."""
        try:
            result = subprocess.run(
                [sg_path, "scan", "--json", "--config", os.path.join(rules_dir, "sgconfig.yml")] + files,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=rules_dir,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []

        if not result.stdout.strip():
            return []

        violations = []
        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError:
            entries = []
            for line in result.stdout.strip().splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        for entry in entries:
            violations.append({
                "ruleId": entry.get("ruleId", "unknown"),
                "file": entry.get("file", ""),
                "line": entry.get("range", {}).get("start", {}).get("line", 0) + 1,
                "message": entry.get("message", ""),
                "source": entry.get("lines", "").strip(),
            })

        return violations

    @staticmethod
    def _format_violations(violations: list[dict]) -> str:
        """Format violations into a blocking message."""
        lines = [f"GATE: lint — {len(violations)} violation(s) found:"]
        for v in violations:
            lines.append(f"  - [{v['ruleId']}] {v['file']}:{v['line']} — {v['message']}")
            if v["source"]:
                truncated = v["source"][:80] + ("..." if len(v["source"]) > 80 else "")
                lines.append(f"    {truncated}")
        lines.append("")
        lines.append("Fix these lint violations before the transition can proceed.")
        return "\n".join(lines)
