"""Детерминированный оценщик."""

from ai_department.domain.evaluation import Trace, TraceStep
from ai_department.domain.risk import RiskLevel
from ai_department.domain.states import VerdictKind
from ai_department.domain.task import ConstraintInput, Task, resolve_constraints
from ai_department.evaluation.deterministic import DeterministicEvaluator


def _task() -> Task:
    return Task(
        goal="проверка",
        constraints=resolve_constraints(
            ConstraintInput(),
            default_steps=20,
            max_steps=100,
            default_revisions=1,
            max_revisions=3,
        ),
        payload={},
        correlation_id="c",
    )


def _trace(steps: tuple[TraceStep, ...], *, max_steps: int = 20) -> Trace:
    return Trace(
        role_id="clerk",
        risk_ceiling=RiskLevel.ACT,
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        max_steps=max_steps,
        steps=steps,
    )


def test_schema_and_limits_pass() -> None:
    verdict = DeterministicEvaluator().evaluate(
        _task(),
        {"summary": "ок"},
        _trace((TraceStep("clerk", "model"),)),
    )
    assert verdict.kind is VerdictKind.PASSED


def test_schema_mismatch_rejects() -> None:
    verdict = DeterministicEvaluator().evaluate(_task(), {"other": 1}, _trace(()))
    assert verdict.kind is VerdictKind.REJECTED
    assert any(check.name == "output_schema" and not check.passed for check in verdict.checks)


def test_act_without_confirmation_rejects() -> None:
    verdict = DeterministicEvaluator().evaluate(
        _task(),
        {"summary": "ок"},
        _trace(
            (
                TraceStep(
                    "clerk",
                    "tool",
                    tool_name="commit_note",
                    risk_level=RiskLevel.ACT,
                    invoked=True,
                    confirmation_consumed=False,
                ),
            )
        ),
    )
    assert verdict.kind is VerdictKind.REJECTED


def test_call_above_ceiling_and_foreign_role_reject() -> None:
    above = DeterministicEvaluator().evaluate(
        _task(),
        {"summary": "ок"},
        _trace(
            (
                TraceStep(
                    "clerk",
                    "tool",
                    tool_name="wipe",
                    risk_level=RiskLevel.DESTRUCTIVE,
                    invoked=True,
                ),
            )
        ),
    )
    foreign = DeterministicEvaluator().evaluate(
        _task(),
        {"summary": "ок"},
        _trace((TraceStep("other", "model"),)),
    )
    assert above.kind is VerdictKind.REJECTED
    assert foreign.kind is VerdictKind.REJECTED


def test_too_many_steps_reject() -> None:
    verdict = DeterministicEvaluator().evaluate(
        _task(),
        {"summary": "ок"},
        _trace((TraceStep("clerk", "model"), TraceStep("clerk", "model")), max_steps=1),
    )
    assert verdict.kind is VerdictKind.REJECTED
