"""Лента прогона. Её читают API и будущая панель."""

from __future__ import annotations

from ai_department.domain.events import Envelope


class RunFeed:
    """Хранит события по run_id и отдаёт их по возрастанию seq."""

    def __init__(self) -> None:
        self._events: dict[str, list[Envelope]] = {}

    def __call__(self, event: Envelope) -> None:
        if not event.run_id:
            return
        self._events.setdefault(event.run_id, []).append(event)

    def list(self, run_id: str) -> list[Envelope]:
        """События прогона, упорядоченные по seq."""
        return sorted(self._events.get(run_id, []), key=lambda item: item.seq)


class ThreadFeed:
    """Хранит события без run_id по correlation_id: разбор сообщения и маршрут приёмной."""

    def __init__(self) -> None:
        self._events: dict[str, list[Envelope]] = {}

    def __call__(self, event: Envelope) -> None:
        if event.run_id or not event.correlation_id:
            return
        self._events.setdefault(event.correlation_id, []).append(event)

    def list(self, thread_id: str) -> list[Envelope]:
        """События треда, упорядоченные по seq."""
        return sorted(self._events.get(thread_id, []), key=lambda item: item.seq)
