"""Приёмная: тред, разбор сообщения, передача оркестратору и ответ."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ai_department.dialog.intake import Dispatch, Intake, IntakeFailure, Reply
from ai_department.dialog.reply import ReplyText, compose_reply
from ai_department.domain.errors import ConfirmationError, ThreadNotFound
from ai_department.domain.events import EventName
from ai_department.domain.run import RunSnapshot
from ai_department.domain.states import EmployeeState
from ai_department.domain.task import Constraints, Task
from ai_department.domain.thread import ReplyKind, ThreadMessage, ThreadPending, ThreadSnapshot
from ai_department.events.bus import EventBus, RunLogger
from ai_department.orchestrator.service import Orchestrator


@dataclass
class _Thread:
    thread_id: str
    messages: list[ThreadMessage] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    pending_run_id: str | None = None


class Reception:
    """Одно окно клиента. Инструменты не вызывает, прогон не завершает."""

    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        intake: Intake,
        bus: EventBus,
        default_constraints: Constraints,
        ids: Callable[[], str],
    ) -> None:
        self._orchestrator = orchestrator
        self._intake = intake
        self._bus = bus
        self._constraints = default_constraints
        self._ids = ids
        self._threads: dict[str, _Thread] = {}

    def open(self) -> ThreadSnapshot:
        """Создаёт пустой тред."""
        thread = _Thread(thread_id=self._ids())
        self._threads[thread.thread_id] = thread
        return self.view(thread.thread_id)

    def view(self, thread_id: str) -> ThreadSnapshot:
        """Снимок треда с ожидающим подтверждением, если оно есть."""
        thread = self._require(thread_id)
        return ThreadSnapshot(
            thread_id=thread.thread_id,
            messages=list(thread.messages),
            run_ids=list(thread.run_ids),
            pending=self._pending(thread),
        )

    def say(self, thread_id: str, text: str) -> ThreadSnapshot:
        """Принимает сообщение, отвечает или создаёт прогон и отвечает по его снимку."""
        thread = self._require(thread_id)
        log = self._log(thread)
        thread.messages.append(ThreadMessage(author="user", text=text))
        log.emit(
            EventName.THREAD_MESSAGE_RECEIVED,
            "Сообщение принято",
            {"thread_id": thread.thread_id, "text": text},
        )
        waiting = self._waiting_snapshot(thread)
        if waiting is not None:
            self._answer(thread, log, compose_reply(waiting), waiting.run_id)
            return self.view(thread_id)
        decision = self._intake.decide(thread.messages, log)
        if isinstance(decision, Reply):
            self._answer(thread, log, ReplyText(ReplyKind.ANSWER, decision.text), None)
            return self.view(thread_id)
        if isinstance(decision, IntakeFailure):
            text = f"Приёмная недоступна: {decision.message}."
            self._answer(thread, log, ReplyText(ReplyKind.FAILED, text), None)
            return self.view(thread_id)
        self._dispatch(thread, log, decision, text)
        return self.view(thread_id)

    def confirm(self, thread_id: str, confirmation_id: str, decision: str) -> ThreadSnapshot:
        """Передаёт approve или reject оркестратору и отвечает по новому снимку."""
        thread = self._require(thread_id)
        if thread.pending_run_id is None:
            raise ConfirmationError("Тред не ждёт подтверждения")
        snapshot = self._orchestrator.confirm(thread.pending_run_id, confirmation_id, decision)
        self._answer(thread, self._log(thread), compose_reply(snapshot), snapshot.run_id)
        return self.view(thread_id)

    def _dispatch(self, thread: _Thread, log: RunLogger, decision: Dispatch, request: str) -> None:
        payload = dict(decision.payload)
        payload.setdefault("channel", decision.role_id)
        payload.setdefault("request", request)
        task = Task(
            goal=decision.goal,
            constraints=self._constraints,
            payload=payload,
            correlation_id=thread.thread_id,
        )
        snapshot = self._orchestrator.submit(task)
        thread.run_ids.append(snapshot.run_id)
        log.emit(
            EventName.THREAD_TASK_DISPATCHED,
            "Задача передана сотруднику",
            {
                "thread_id": thread.thread_id,
                "run_id": snapshot.run_id,
                "goal": task.goal,
                "payload": payload,
            },
        )
        self._answer(thread, log, compose_reply(snapshot), snapshot.run_id)

    def _answer(
        self, thread: _Thread, log: RunLogger, reply: ReplyText, run_id: str | None
    ) -> None:
        if run_id is not None and reply.kind is ReplyKind.WAITING_CONFIRMATION:
            thread.pending_run_id = run_id
        else:
            thread.pending_run_id = None
        thread.messages.append(
            ThreadMessage(author="assistant", text=reply.text, run_id=run_id, kind=reply.kind)
        )
        log.emit(
            EventName.THREAD_REPLIED,
            "Ответ клиенту",
            {
                "thread_id": thread.thread_id,
                "run_id": run_id or "",
                "kind": reply.kind.value,
                "text": reply.text,
            },
        )

    def _waiting_snapshot(self, thread: _Thread) -> RunSnapshot | None:
        if thread.pending_run_id is None:
            return None
        snapshot = self._orchestrator.snapshot(thread.pending_run_id)
        if snapshot.state is EmployeeState.WAITING_CONFIRMATION:
            return snapshot
        thread.pending_run_id = None
        return None

    def _pending(self, thread: _Thread) -> ThreadPending | None:
        snapshot = self._waiting_snapshot(thread)
        if snapshot is None or snapshot.pending_confirmation is None:
            return None
        view = snapshot.pending_confirmation
        return ThreadPending(
            run_id=snapshot.run_id,
            confirmation_id=view.confirmation_id,
            tool=view.tool,
            arguments=dict(view.arguments),
        )

    def _log(self, thread: _Thread) -> RunLogger:
        return RunLogger(bus=self._bus, run_id="", correlation_id=thread.thread_id)

    def _require(self, thread_id: str) -> _Thread:
        thread = self._threads.get(thread_id)
        if thread is None:
            raise ThreadNotFound(thread_id)
        return thread
