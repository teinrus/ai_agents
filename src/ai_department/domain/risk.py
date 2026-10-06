"""Уровни риска. Роль может только сузить потолок."""

from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    """Уровни по возрастанию: read < draft < act < destructive."""

    READ = "read"
    DRAFT = "draft"
    ACT = "act"
    DESTRUCTIVE = "destructive"


_RANK: dict[RiskLevel, int] = {
    RiskLevel.READ: 0,
    RiskLevel.DRAFT: 1,
    RiskLevel.ACT: 2,
    RiskLevel.DESTRUCTIVE: 3,
}


def risk_rank(level: RiskLevel) -> int:
    """Числовой ранг уровня."""
    return _RANK[level]


def exceeds(level: RiskLevel, ceiling: RiskLevel) -> bool:
    """Истина, если уровень выше потолка."""
    return risk_rank(level) > risk_rank(ceiling)


def parse_risk(value: str) -> RiskLevel:
    """Читает уровень из конфигурации."""
    try:
        return RiskLevel(value)
    except ValueError as exc:
        raise ValueError(f"Неизвестный уровень риска: {value}") from exc
