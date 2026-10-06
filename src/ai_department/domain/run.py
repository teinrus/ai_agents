"""Снимок прогона для API. Состояние сотрудника читается отдельно."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_department.domain.states import EmployeeState, RunStatus


@dataclass(frozen=True)
class PendingView:
    """Ожидающее подтверждение без секретов и без одноразового хеша."""

    confirmation_id: str
    tool: str
    arguments: dict[str, Any]


@dataclass
class RunSnapshot:
    """Поля прогона, которые отдаёт сервис приложения."""

    run_id: str
    correlation_id: str
    status: RunStatus | None
    state: EmployeeState | None
    role_id: str | None
    failure_reason: str | None
    pending_confirmation: PendingView | None
    step_count: int
    revision_count: int
    output: object | None
