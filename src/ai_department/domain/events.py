"""Конверт события и имена из контракта шины."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class EventLevel(StrEnum):
    """Уровень конверта."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class EventName(StrEnum):
    """Имена событий. Синонимы не заводятся."""

    TASK_RECEIVED = "task.received"
    AGENT_SELECTED = "agent.selected"
    AGENT_STATE_CHANGED = "agent.state_changed"
    SKILL_BOUND = "skill.bound"
    MODEL_ROUTED = "model.routed"
    MODEL_CALLED = "model.called"
    MODEL_FAILED = "model.failed"
    TOOL_INVOKED = "tool.invoked"
    TOOL_DENIED = "tool.denied"
    TOOL_CONFIRMATION_REQUIRED = "tool.confirmation_required"
    TOOL_FAILED = "tool.failed"
    EVALUATION_STARTED = "evaluation.started"
    EVALUATION_REVISION_REQUESTED = "evaluation.revision_requested"
    EVALUATION_COMPLETED = "evaluation.completed"
    TASK_FINISHED = "task.finished"
    THREAD_MESSAGE_RECEIVED = "thread.message_received"
    THREAD_TASK_DISPATCHED = "thread.task_dispatched"
    THREAD_REPLIED = "thread.replied"


EVENT_LEVELS: dict[EventName, EventLevel] = {
    EventName.TASK_RECEIVED: EventLevel.INFO,
    EventName.AGENT_SELECTED: EventLevel.INFO,
    EventName.AGENT_STATE_CHANGED: EventLevel.INFO,
    EventName.SKILL_BOUND: EventLevel.INFO,
    EventName.MODEL_ROUTED: EventLevel.INFO,
    EventName.MODEL_CALLED: EventLevel.INFO,
    EventName.MODEL_FAILED: EventLevel.ERROR,
    EventName.TOOL_INVOKED: EventLevel.INFO,
    EventName.TOOL_DENIED: EventLevel.WARNING,
    EventName.TOOL_CONFIRMATION_REQUIRED: EventLevel.WARNING,
    EventName.TOOL_FAILED: EventLevel.ERROR,
    EventName.EVALUATION_STARTED: EventLevel.INFO,
    EventName.EVALUATION_REVISION_REQUESTED: EventLevel.INFO,
    EventName.EVALUATION_COMPLETED: EventLevel.INFO,
    EventName.TASK_FINISHED: EventLevel.INFO,
    EventName.THREAD_MESSAGE_RECEIVED: EventLevel.INFO,
    EventName.THREAD_TASK_DISPATCHED: EventLevel.INFO,
    EventName.THREAD_REPLIED: EventLevel.INFO,
}

EVENT_NAMES: frozenset[str] = frozenset(item.value for item in EventName)


@dataclass(frozen=True)
class Envelope:
    """Общий конверт для ленты, счётчиков и будущего брокера."""

    ts: str
    seq: int
    level: EventLevel
    correlation_id: str
    run_id: str
    event: str
    role_id: str | None
    step: int | None
    message: str
    payload: dict[str, Any]


class EventLog(Protocol):
    """Публикатор одного прогона. Не знает подписчиков."""

    run_id: str
    correlation_id: str
    role_id: str | None

    def emit(
        self,
        event: EventName,
        message: str,
        payload: Mapping[str, Any],
        *,
        role_id: str | None = None,
        step: int | None = None,
    ) -> None:
        """Публикует событие с уровнем из контракта."""


def envelope_dict(event: Envelope) -> dict[str, object]:
    """Поля конверта для stdout и HTTP."""
    return {
        "ts": event.ts,
        "seq": event.seq,
        "level": event.level.value,
        "correlation_id": event.correlation_id,
        "run_id": event.run_id,
        "event": event.event,
        "role_id": event.role_id,
        "step": event.step,
        "message": event.message,
        "payload": event.payload,
    }
