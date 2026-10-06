"""Вердикт оценки и трасса шагов."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ai_department.domain.risk import RiskLevel
from ai_department.domain.states import VerdictKind


@dataclass(frozen=True)
class CheckResult:
    """Одна проверка оценщика."""

    name: str
    passed: bool
    remark: str


@dataclass(frozen=True)
class Verdict:
    """Итог Evaluator.evaluate."""

    kind: VerdictKind
    checks: tuple[CheckResult, ...]


@dataclass(frozen=True)
class TraceStep:
    """Шаг трассы: вызов модели или исполненный инструмент."""

    role_id: str
    kind: str
    tool_name: str | None = None
    risk_level: RiskLevel | None = None
    invoked: bool = False
    confirmation_consumed: bool = False


@dataclass(frozen=True)
class Trace:
    """Вход детерминированного оценщика без домена роли."""

    role_id: str
    risk_ceiling: RiskLevel
    output_schema: Mapping[str, object]
    max_steps: int
    steps: tuple[TraceStep, ...]
    bound_tools: frozenset[str] = frozenset()


def verdict_payload(verdict: Verdict) -> dict[str, object]:
    """Поля вердикта для evaluation.completed."""
    return {
        "verdict": verdict.kind.value,
        "checks": [
            {"name": check.name, "passed": check.passed, "remark": check.remark}
            for check in verdict.checks
        ],
    }


def failed_remarks(verdict: Verdict) -> list[dict[str, str]]:
    """Структурированные замечания для правки."""
    return [
        {"name": check.name, "remark": check.remark} for check in verdict.checks if not check.passed
    ]
