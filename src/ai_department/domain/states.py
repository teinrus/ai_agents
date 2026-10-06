"""Состояния сотрудника и статусы прогона."""

from __future__ import annotations

from enum import StrEnum


class EmployeeState(StrEnum):
    """Состояния автомата сотрудника."""

    REGISTERED = "Registered"
    IDLE = "Idle"
    ASSIGNED = "Assigned"
    RUNNING = "Running"
    WAITING_TOOL = "WaitingTool"
    WAITING_MODEL = "WaitingModel"
    WAITING_CONFIRMATION = "WaitingConfirmation"
    EVALUATING = "Evaluating"
    COMPLETED = "Completed"
    FAILED = "Failed"
    RETIRED = "Retired"


class RunStatus(StrEnum):
    """Терминальный статус прогона."""

    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    NO_ROLE = "no_role"


class PolicyDecision(StrEnum):
    """Ответ политики инструментов."""

    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class VerdictKind(StrEnum):
    """Итог оценки."""

    PASSED = "passed"
    REJECTED = "rejected"
