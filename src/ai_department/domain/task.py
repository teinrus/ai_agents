"""Вход прогона: задача и ограничения."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ai_department.domain.errors import ValidationError


@dataclass(frozen=True)
class Constraints:
    """Пределы одного прогона после подстановки дефолтов."""

    max_steps: int
    max_revisions: int
    deadline: datetime | None = None


@dataclass(frozen=True)
class ConstraintInput:
    """Сырые ограничения клиента. Пустые поля заполняет платформа."""

    max_steps: int | None = None
    max_revisions: int | None = None
    deadline: datetime | None = None


@dataclass(frozen=True)
class Task:
    """Задача клиента. Payload непрозрачен для ядра."""

    goal: str
    constraints: Constraints
    payload: dict[str, Any]
    correlation_id: str


def resolve_constraints(
    raw: ConstraintInput,
    *,
    default_steps: int,
    max_steps: int,
    default_revisions: int,
    max_revisions: int,
) -> Constraints:
    """Подставляет дефолты. Значение выше максимума — ошибка, не урезание."""
    steps = default_steps if raw.max_steps is None else raw.max_steps
    revisions = default_revisions if raw.max_revisions is None else raw.max_revisions
    if steps < 1 or steps > max_steps:
        raise ValidationError(f"max_steps должно быть от 1 до {max_steps}")
    if revisions < 0 or revisions > max_revisions:
        raise ValidationError(f"max_revisions должно быть от 0 до {max_revisions}")
    deadline = raw.deadline
    if deadline is not None and deadline.tzinfo is None:
        raise ValidationError("deadline должен быть с часовым поясом")
    return Constraints(max_steps=steps, max_revisions=revisions, deadline=deadline)


def constraints_payload(constraints: Constraints) -> dict[str, object]:
    """Безопасное представление ограничений для шины."""
    deadline = None if constraints.deadline is None else constraints.deadline.isoformat()
    return {
        "max_steps": constraints.max_steps,
        "max_revisions": constraints.max_revisions,
        "deadline": deadline,
    }
