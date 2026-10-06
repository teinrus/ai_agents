"""Схемы HTTP. Наружу — поля прогона и конверта, не типы SDK."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConstraintsIn(BaseModel):
    """Необязательные пределы задачи."""

    max_steps: int | None = None
    max_revisions: int | None = None
    deadline: datetime | None = None


class TaskIn(BaseModel):
    """Тело создания задачи."""

    goal: str = Field(min_length=1)
    constraints: ConstraintsIn | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class TaskCreated(BaseModel):
    """Идентификаторы принятого прогона."""

    run_id: str
    correlation_id: str


class PendingOut(BaseModel):
    """Ожидающее подтверждение."""

    confirmation_id: str
    tool: str
    arguments: dict[str, Any]


class RunOut(BaseModel):
    """Состояние сотрудника, статус и подтверждение, если оно есть."""

    run_id: str
    correlation_id: str
    status: str | None
    state: str | None
    role_id: str | None
    failure_reason: str | None
    pending_confirmation: PendingOut | None
    step_count: int
    revision_count: int
    output: Any | None


class ConfirmationIn(BaseModel):
    """Ответ клиента на confirmation_id."""

    confirmation_id: str
    decision: Literal["approve", "reject"]


class ThreadCreated(BaseModel):
    """Идентификатор открытого треда."""

    thread_id: str


class MessageIn(BaseModel):
    """Сообщение клиента в тред."""

    text: str = Field(min_length=1)


class ThreadMessageOut(BaseModel):
    """Сообщение треда."""

    author: str
    text: str
    run_id: str | None
    kind: str | None


class ThreadPendingOut(BaseModel):
    """Подтверждение, которого ждёт прогон треда."""

    run_id: str
    confirmation_id: str
    tool: str
    arguments: dict[str, Any]


class ThreadOut(BaseModel):
    """Сообщения, связанные прогоны и ожидающее подтверждение."""

    thread_id: str
    messages: list[ThreadMessageOut]
    run_ids: list[str]
    pending: ThreadPendingOut | None
