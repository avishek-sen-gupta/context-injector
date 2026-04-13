# gates/lint.py
"""LintGate — ast-grep based lint checking at transition boundaries.

Runs ast-grep with project lint rules on recently modified Python files.
Blocks the transition if any violations are found.
"""

import json
import os
import shutil
import subprocess

from gates.base import Gate, GateContext, GateResult, GateVerdict


class LintGate(Gate):
    """Gate that runs ast-grep lint rules on touched files."""

    name = "lint"

    def __init__(self, rules_dir: str | None = None):
        self.rules_dir = rules_dir

    def evaluate(self, ctx: GateContext) -> GateResult:
        py_files = self._filter_python_files(ctx.recent_files)
        if not py_files:
            return GateResult(GateVerdict.PASS)

        sg = self._find_sg()
        if sg is None:
            return GateResult(GateVerdict.PASS)

        rules_dir = self._resolve_rules_dir(ctx.project_root)
        if rules_dir is None:
            return GateResult(GateVerdict.PASS)

        violations = self._run_sg(sg, rules_dir, py_files)
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
    def _find_sg() -> str | None:
        """Find the ast-grep binary."""
        return shutil.which("sg") or shutil.which("ast-grep")

    def _resolve_rules_dir(self, project_root: str) -> str | None:
        """Find the lint rules directory.

        Searches in order: explicit rules_dir, project-local scripts/lint/,
        then CTX_LINT_RULES_DIR (set by the governor hooks at install time).
        """
        if self.rules_dir:
            return self.rules_dir
        candidates = [
            os.path.join(project_root, "scripts", "lint"),
        ]
        env_dir = os.environ.get("CTX_LINT_RULES_DIR")
        if env_dir:
            candidates.append(env_dir)
        for candidate in candidates:
            if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "sgconfig.yml")):
                return candidate
        return None

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
        # ast-grep --json outputs a JSON array
        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Fall back to JSONL (one object per line)
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
