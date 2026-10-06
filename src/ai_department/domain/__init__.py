"""Доменные типы контракта. Пакет не зависит от остальной платформы."""

from ai_department.domain.errors import (
    ConfigError,
    ConfirmationError,
    InvalidTransition,
    MemoryAccessError,
    NoModelError,
    PlatformError,
    ProviderError,
    RunNotFound,
    ValidationError,
)
from ai_department.domain.events import Envelope, EventLog, EventName
from ai_department.domain.role import RolePlugin, SkillSpec
from ai_department.domain.states import EmployeeState, RunStatus
from ai_department.domain.task import Task

__all__ = [
    "ConfigError",
    "ConfirmationError",
    "EmployeeState",
    "Envelope",
    "EventLog",
    "EventName",
    "InvalidTransition",
    "MemoryAccessError",
    "NoModelError",
    "PlatformError",
    "ProviderError",
    "RolePlugin",
    "RunNotFound",
    "RunStatus",
    "SkillSpec",
    "Task",
    "ValidationError",
]
