"""Таблица переходов. Новое ребро появляется только вместе со спекой."""

from __future__ import annotations

from ai_department.domain.errors import InvalidTransition
from ai_department.domain.states import EmployeeState

ALLOWED: frozenset[tuple[EmployeeState, EmployeeState]] = frozenset(
    {
        (EmployeeState.REGISTERED, EmployeeState.IDLE),
        (EmployeeState.IDLE, EmployeeState.ASSIGNED),
        (EmployeeState.ASSIGNED, EmployeeState.RUNNING),
        (EmployeeState.RUNNING, EmployeeState.WAITING_MODEL),
        (EmployeeState.WAITING_MODEL, EmployeeState.RUNNING),
        (EmployeeState.WAITING_MODEL, EmployeeState.FAILED),
        (EmployeeState.RUNNING, EmployeeState.WAITING_TOOL),
        (EmployeeState.WAITING_TOOL, EmployeeState.RUNNING),
        (EmployeeState.RUNNING, EmployeeState.WAITING_CONFIRMATION),
        (EmployeeState.WAITING_CONFIRMATION, EmployeeState.RUNNING),
        (EmployeeState.WAITING_CONFIRMATION, EmployeeState.FAILED),
        (EmployeeState.RUNNING, EmployeeState.EVALUATING),
        (EmployeeState.RUNNING, EmployeeState.FAILED),
        (EmployeeState.EVALUATING, EmployeeState.RUNNING),
        (EmployeeState.EVALUATING, EmployeeState.COMPLETED),
        (EmployeeState.EVALUATING, EmployeeState.FAILED),
        (EmployeeState.COMPLETED, EmployeeState.IDLE),
        (EmployeeState.FAILED, EmployeeState.IDLE),
        (EmployeeState.IDLE, EmployeeState.RETIRED),
    }
)


def ensure_transition(source: EmployeeState, target: EmployeeState) -> None:
    """Разрешает переход только если пара есть в контракте."""
    if (source, target) not in ALLOWED:
        raise InvalidTransition(source.value, target.value)


def automatic_idle(state: EmployeeState) -> EmployeeState | None:
    """Completed и Failed в том же такте возвращают сотрудника в Idle."""
    if state in {EmployeeState.COMPLETED, EmployeeState.FAILED}:
        return EmployeeState.IDLE
    return None
