import pytest
from gates.base import Gate, GateResult, GateVerdict, GateContext


class TestGateVerdict:
    def test_pass_value(self):
        assert GateVerdict.PASS == "pass"

    def test_fail_value(self):
        assert GateVerdict.FAIL == "fail"

    def test_review_value(self):
        assert GateVerdict.REVIEW == "review"


class TestGateResult:
    def test_pass_result(self):
        r = GateResult(GateVerdict.PASS)
        assert r.verdict == GateVerdict.PASS
        assert r.message is None
        assert r.issues == []

    def test_fail_result_with_message(self):
        r = GateResult(GateVerdict.FAIL, message="bad test", issues=["no_assertions"])
        assert r.verdict == GateVerdict.FAIL
        assert r.message == "bad test"
        assert r.issues == ["no_assertions"]

    def test_review_result(self):
        r = GateResult(GateVerdict.REVIEW, message="check this", issues=["weak"])
        assert r.verdict == GateVerdict.REVIEW


class TestGateContext:
    def test_context_fields(self):
        ctx = GateContext(
            state_name="writing_tests",
            transition_name="pytest_fail",
            recent_tools=["Write(/tmp/tests/test_foo.py)"],
            recent_files=["/tmp/tests/test_foo.py"],
            machine=None,
            project_root="/tmp/project",
        )
        assert ctx.state_name == "writing_tests"
        assert ctx.transition_name == "pytest_fail"
        assert ctx.recent_files == ["/tmp/tests/test_foo.py"]
        assert ctx.project_root == "/tmp/project"


class TestGateBase:
    def test_base_gate_has_name(self):
        g = Gate()
        assert g.name == "unnamed"

    def test_base_gate_evaluate_raises(self):
        g = Gate()
        ctx = GateContext(
            state_name="s", transition_name="t",
            recent_tools=[], recent_files=[],
            machine=None, project_root="/tmp",
        )
        with pytest.raises(NotImplementedError):
            g.evaluate(ctx)
