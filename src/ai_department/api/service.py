"""Сервис края: оркестратор и лента, без правил риска и оценки."""

from __future__ import annotations

from datetime import datetime

from ai_department.dialog.reception import Reception
from ai_department.domain.events import Envelope, envelope_dict
from ai_department.domain.run import RunSnapshot
from ai_department.domain.task import ConstraintInput, Task, resolve_constraints
from ai_department.domain.thread import ThreadSnapshot, ThreadSummary
from ai_department.llm.catalog import ModelCatalog
from ai_department.observability.feed import RunFeed, ThreadFeed
from ai_department.orchestrator.service import Orchestrator

EventList = list[Envelope]


class HealthApi:
    """Состояние платформы: адаптеры, роли, сотрудники. Модель и инструменты не трогает."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        catalog: ModelCatalog,
        *,
        llm_adapter: str,
        memory_backend: str,
        threads_backend: str,
    ) -> None:
        self._orchestrator = orchestrator
        self._catalog = catalog
        self._llm_adapter = llm_adapter
        self._memory_backend = memory_backend
        self._threads_backend = threads_backend

    def read(self) -> dict[str, object]:
        return {
            "status": "ok",
            "llm_adapter": self._llm_adapter,
            "memory_backend": self._memory_backend,
            "threads_backend": self._threads_backend,
            "catalog_models": len(self._catalog.list()),
            "roles": [
                {"role_id": plugin.role_id, "description": plugin.description, "state": state.value}
                for plugin, state in self._orchestrator.staff()
            ],
        }


class RunApi:
    """Тонкая обёртка над оркестратором."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        feed: RunFeed,
        *,
        default_steps: int,
        max_steps: int,
        default_revisions: int,
        max_revisions: int,
    ) -> None:
        self._orchestrator = orchestrator
        self._feed = feed
        self._default_steps = default_steps
        self._max_steps = max_steps
        self._default_revisions = default_revisions
        self._max_revisions = max_revisions

    def create_task(
        self,
        *,
        goal: str,
        payload: dict[str, object],
        correlation_id: str | None,
        max_steps: int | None,
        max_revisions: int | None,
        deadline: datetime | None,
    ) -> RunSnapshot:
        constraints = resolve_constraints(
            ConstraintInput(
                max_steps=max_steps,
                max_revisions=max_revisions,
                deadline=deadline,
            ),
            default_steps=self._default_steps,
            max_steps=self._max_steps,
            default_revisions=self._default_revisions,
            max_revisions=self._max_revisions,
        )
        task = Task(
            goal=goal,
            constraints=constraints,
            payload=dict(payload),
            correlation_id=correlation_id or "",
        )
        return self._orchestrator.submit(task)

    def get_run(self, run_id: str) -> RunSnapshot:
        return self._orchestrator.snapshot(run_id)

    def get_events(self, run_id: str) -> list[Envelope]:
        self._orchestrator.snapshot(run_id)
        return self._feed.list(run_id)

    def confirm(self, run_id: str, confirmation_id: str, decision: str) -> RunSnapshot:
        return self._orchestrator.confirm(run_id, confirmation_id, decision)


class ThreadApi:
    """Тонкая обёртка над приёмной."""

    def __init__(self, reception: Reception, feed: ThreadFeed) -> None:
        self._reception = reception
        self._feed = feed

    def open(self) -> ThreadSnapshot:
        return self._reception.open()

    def list(self) -> list[ThreadSummary]:
        return self._reception.list()

    def get_thread(self, thread_id: str) -> ThreadSnapshot:
        return self._reception.view(thread_id)

    def say(self, thread_id: str, text: str) -> ThreadSnapshot:
        return self._reception.say(thread_id, text)

    def confirm(self, thread_id: str, confirmation_id: str, decision: str) -> ThreadSnapshot:
        return self._reception.confirm(thread_id, confirmation_id, decision)

    def get_events(self, thread_id: str) -> EventList:
        self._reception.view(thread_id)
        return self._feed.list(thread_id)


def thread_payload(snapshot: ThreadSnapshot) -> dict[str, object]:
    """Словарь ответа треда."""
    pending = snapshot.pending
    return {
        "thread_id": snapshot.thread_id,
        "messages": [
            {
                "author": item.author,
                "text": item.text,
                "run_id": item.run_id,
                "kind": None if item.kind is None else item.kind.value,
            }
            for item in snapshot.messages
        ],
        "run_ids": list(snapshot.run_ids),
        "pending": None
        if pending is None
        else {
            "run_id": pending.run_id,
            "confirmation_id": pending.confirmation_id,
            "tool": pending.tool,
            "arguments": pending.arguments,
        },
    }


def run_payload(snapshot: RunSnapshot) -> dict[str, object]:
    """Словарь ответа прогона."""
    pending = snapshot.pending_confirmation
    return {
        "run_id": snapshot.run_id,
        "correlation_id": snapshot.correlation_id,
        "status": None if snapshot.status is None else snapshot.status.value,
        "state": None if snapshot.state is None else snapshot.state.value,
        "role_id": snapshot.role_id,
        "failure_reason": snapshot.failure_reason,
        "pending_confirmation": None
        if pending is None
        else {
            "confirmation_id": pending.confirmation_id,
            "tool": pending.tool,
            "arguments": pending.arguments,
        },
        "step_count": snapshot.step_count,
        "revision_count": snapshot.revision_count,
        "output": snapshot.output,
    }


def event_payloads(events: list[Envelope]) -> list[dict[str, object]]:
    """Список конвертов."""
    return [envelope_dict(event) for event in events]
