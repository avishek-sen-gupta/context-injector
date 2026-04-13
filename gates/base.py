"""Base classes for transition guards.

A Gate is a check that runs when a state machine transition is about to fire.
It inspects the work done during the current state and decides whether the
transition should proceed (PASS), be blocked (FAIL), or require review (REVIEW).
"""

from enum import Enum


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"


class GateResult:
    """Result of a gate evaluation."""

    def __init__(
        self,
        verdict: GateVerdict,
        message: str | None = None,
        issues: list[str] | None = None,
    ):
        self.verdict = verdict
        self.message = message
        self.issues = issues or []


class GateContext:
    """Context passed to gates for evaluation."""

    def __init__(
        self,
        state_name: str,
        transition_name: str,
        recent_tools: list[str],
        recent_files: list[str],
        machine,
        project_root: str,
    ):
        self.state_name = state_name
        self.transition_name = transition_name
        self.recent_tools = recent_tools
        self.recent_files = recent_files
        self.machine = machine
        self.project_root = project_root


class Gate:
    """Base class for transition guards."""

    name: str = "unnamed"

    def evaluate(self, context: GateContext) -> GateResult:
        raise NotImplementedError
