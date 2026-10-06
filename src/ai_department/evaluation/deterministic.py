"""Проверки без домена роли."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ai_department.domain.evaluation import CheckResult, Trace, Verdict
from ai_department.domain.risk import RiskLevel, exceeds
from ai_department.domain.states import VerdictKind
from ai_department.domain.task import Task


class DeterministicEvaluator:
    """Схема, лимит шагов, подтверждение act, потолок, роль трассы и след инструментов."""

    def evaluate(self, task: Task, output: object, trace: Trace) -> Verdict:
        del task
        checks = (
            _schema(output, trace.output_schema),
            _steps(trace),
            _confirmations(trace),
            _ceiling(trace),
            _role(trace),
            _tool_evidence(trace),
        )
        kind = VerdictKind.PASSED if all(check.passed for check in checks) else VerdictKind.REJECTED
        return Verdict(kind=kind, checks=checks)


def _schema(output: object, schema: Mapping[str, object]) -> CheckResult:
    try:
        validator = Draft202012Validator(cast(dict[str, Any], dict(schema)))
        errors = sorted(validator.iter_errors(output), key=lambda item: str(list(item.path)))
    except SchemaError as exc:
        return CheckResult("output_schema", False, f"Схема роли некорректна: {exc.message}")
    if not errors:
        return CheckResult("output_schema", True, "")
    return CheckResult("output_schema", False, errors[0].message)


def _steps(trace: Trace) -> CheckResult:
    count = len(trace.steps)
    if count <= trace.max_steps:
        return CheckResult("max_steps", True, "")
    return CheckResult("max_steps", False, f"Шагов {count}, лимит {trace.max_steps}")


def _confirmations(trace: Trace) -> CheckResult:
    for step in trace.steps:
        if step.invoked and step.risk_level is RiskLevel.ACT and not step.confirmation_consumed:
            return CheckResult("act_confirmation", False, f"act {step.tool_name} без подтверждения")
    return CheckResult("act_confirmation", True, "")


def _ceiling(trace: Trace) -> CheckResult:
    for step in trace.steps:
        if (
            step.invoked
            and step.risk_level is not None
            and exceeds(step.risk_level, trace.risk_ceiling)
        ):
            return CheckResult("risk_ceiling", False, f"{step.tool_name} выше потолка роли")
    return CheckResult("risk_ceiling", True, "")


def _tool_evidence(trace: Trace) -> CheckResult:
    if not trace.bound_tools or any(step.kind == "tool" for step in trace.steps):
        return CheckResult("tool_evidence", True, "")
    return CheckResult(
        "tool_evidence",
        False,
        "Ни один инструмент не вызван. Сделай задачу инструментами, а не описанием результата",
    )


def _role(trace: Trace) -> CheckResult:
    for step in trace.steps:
        if step.role_id != trace.role_id:
            return CheckResult("role_id", False, "В трассе чужая роль")
    return CheckResult("role_id", True, "")
