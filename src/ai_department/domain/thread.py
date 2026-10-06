"""Тред диалога: сообщения, связанные прогоны и вид ответа."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReplyKind(StrEnum):
    """Вид ответа приёмной. Таблица — раздел 19.3 контракта."""

    ANSWER = "answer"
    COMPLETED = "completed"
    WAITING_CONFIRMATION = "waiting_confirmation"
    NO_ROLE = "no_role"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class ThreadMessage:
    """Одно сообщение треда. У ответов есть kind, у задач — run_id."""

    author: str
    text: str
    run_id: str | None = None
    kind: ReplyKind | None = None


@dataclass(frozen=True)
class ThreadPending:
    """Подтверждение, которого ждёт прогон треда."""

    run_id: str
    confirmation_id: str
    tool: str
    arguments: dict[str, Any]


@dataclass
class ThreadSnapshot:
    """Поля треда, которые отдаёт сервис приложения."""

    thread_id: str
    messages: list[ThreadMessage] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    pending: ThreadPending | None = None
