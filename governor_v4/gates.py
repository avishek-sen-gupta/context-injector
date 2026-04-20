"""Evidence gates: validate transition claims against locker evidence."""

from enum import Enum

from governor_v4.locker import EvidenceLocker


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class GateResult:
    """Result of a gate validation."""

    def __init__(self, verdict: GateVerdict, message: str | None = None):
        self.verdict = verdict
        self.message = message


class EvidenceGate:
    """Base class for evidence gates. Receives key(s) + locker access."""

    name: str = "unnamed"
    required_type: str = ""

    def validate(self, evidence_keys: list[str], locker: EvidenceLocker) -> GateResult:
        raise NotImplementedError


class _TypeCheckGate(EvidenceGate):
    """Trust-mode gate: checks evidence exists and type matches."""

    def validate(self, evidence_keys: list[str], locker: EvidenceLocker) -> GateResult:
        for key in evidence_keys:
            entry = locker.retrieve(key)
            if entry and entry.get("type") == self.required_type:
                return GateResult(GateVerdict.PASS)
        return GateResult(
            GateVerdict.FAIL,
            f"No {self.required_type} evidence found for keys: {evidence_keys}",
        )


class PytestFailGate(_TypeCheckGate):
    name = "pytest_fail_gate"
    required_type = "pytest_output"


class PytestPassGate(_TypeCheckGate):
    name = "pytest_pass_gate"
    required_type = "pytest_output"


class LintFailGate(_TypeCheckGate):
    name = "lint_fail_gate"
    required_type = "lint_output"


class LintPassGate(_TypeCheckGate):
    name = "lint_pass_gate"
    required_type = "lint_output"


GATE_REGISTRY: dict[str, type[EvidenceGate]] = {
    "pytest_fail_gate": PytestFailGate,
    "pytest_pass_gate": PytestPassGate,
    "lint_fail_gate": LintFailGate,
    "lint_pass_gate": LintPassGate,
}
