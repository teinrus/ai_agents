"""Чистая политика. Первое совпавшее правило решает. Ошибка — deny."""

from __future__ import annotations

from dataclasses import dataclass

from ai_department.domain.risk import RiskLevel, exceeds
from ai_department.domain.states import PolicyDecision


@dataclass(frozen=True)
class PolicyCall:
    """Вызов, который видит политика."""

    name: str
    risk_level: RiskLevel
    has_grant: bool


@dataclass(frozen=True)
class PolicyContext:
    """Контекст прогона. Потолок отсюда не поднимается."""

    run_id: str
    role_id: str
    bound_tools: frozenset[str]
    role_ceiling: RiskLevel
    platform_ceiling: RiskLevel


@dataclass(frozen=True)
class PolicyResult:
    """Решение и номер правила контракта."""

    decision: PolicyDecision
    rule: int


def decide(call: PolicyCall, context: PolicyContext) -> PolicyResult:
    """Возвращает allow, confirm или deny. Исключение наружу не выходит."""
    try:
        return _decide(call, context)
    except Exception:
        return PolicyResult(PolicyDecision.DENY, 0)


def _decide(call: PolicyCall, context: PolicyContext) -> PolicyResult:
    if call.name not in context.bound_tools:
        return PolicyResult(PolicyDecision.DENY, 1)
    if exceeds(call.risk_level, context.role_ceiling) or exceeds(
        call.risk_level, context.platform_ceiling
    ):
        return PolicyResult(PolicyDecision.DENY, 2)
    if call.risk_level is RiskLevel.DESTRUCTIVE:
        return PolicyResult(PolicyDecision.DENY, 3)
    if call.risk_level in {RiskLevel.READ, RiskLevel.DRAFT}:
        return PolicyResult(PolicyDecision.ALLOW, 4)
    if call.risk_level is RiskLevel.ACT:
        if call.has_grant:
            return PolicyResult(PolicyDecision.ALLOW, 5)
        return PolicyResult(PolicyDecision.CONFIRM, 5)
    return PolicyResult(PolicyDecision.DENY, 0)
