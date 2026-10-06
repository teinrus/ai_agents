"""Синхронная шина. Публикатор не знает подписчиков."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ai_department.domain.events import (
    EVENT_LEVELS,
    EVENT_NAMES,
    Envelope,
    EventLog,
    EventName,
)
from ai_department.events.redaction import redact_payload

Subscriber = Callable[[Envelope], None]


def utc_iso(moment: datetime) -> str:
    """UTC в ISO-8601."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


class EventBus:
    """Внутрипроцессная синхронная шина. seq растёт внутри run_id."""

    def __init__(self, *, clock: Callable[[], datetime], debug: bool) -> None:
        self._clock = clock
        self._debug = debug
        self._subscribers: list[Subscriber] = []
        self._seq: dict[str, int] = {}

    def subscribe(self, subscriber: Subscriber) -> None:
        """Подключает подписчика. Отключение — просто не подключать."""
        self._subscribers.append(subscriber)

    def publish(self, draft: Envelope) -> Envelope | None:
        """Нумерует конверт, редактирует payload и отдаёт подписчикам."""
        if draft.event not in EVENT_NAMES:
            raise ValueError(f"Неизвестное событие: {draft.event}")
        if draft.level.value == "DEBUG" and not self._debug:
            return None
        seq = self._seq.get(draft.run_id, 0) + 1
        self._seq[draft.run_id] = seq
        ready = Envelope(
            ts=utc_iso(self._clock()),
            seq=seq,
            level=draft.level,
            correlation_id=draft.correlation_id,
            run_id=draft.run_id,
            event=draft.event,
            role_id=draft.role_id,
            step=draft.step,
            message=draft.message,
            payload=redact_payload(draft.payload),
        )
        for subscriber in self._subscribers:
            subscriber(ready)
        return ready


@dataclass
class RunLogger:
    """Журнал одного прогона или платформенного перехода вне прогона."""

    bus: EventBus
    run_id: str
    correlation_id: str
    role_id: str | None = None

    def emit(
        self,
        event: EventName,
        message: str,
        payload: Mapping[str, Any],
        *,
        role_id: str | None = None,
        step: int | None = None,
    ) -> None:
        """Публикует событие. Уровень берётся из таблицы контракта."""
        bound_role = self.role_id if role_id is None else role_id
        self.bus.publish(
            Envelope(
                ts="",
                seq=0,
                level=EVENT_LEVELS[event],
                correlation_id=self.correlation_id,
                run_id=self.run_id,
                event=event.value,
                role_id=bound_role,
                step=step,
                message=message,
                payload=dict(payload),
            )
        )


def _assert_log(_: EventLog) -> None:
    """Фиксирует, что RunLogger удовлетворяет протоколу."""
    return None
