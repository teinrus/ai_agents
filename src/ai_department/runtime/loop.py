"""Общий цикл шагов. Не выбирает роль и не оценивает результат."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ai_department.domain.errors import NoModelError, ProviderError
from ai_department.domain.evaluation import TraceStep
from ai_department.domain.events import EventName
from ai_department.domain.states import EmployeeState
from ai_department.domain.tools import ToolCall
from ai_department.llm.port import ChatMessage, LlmResponse
from ai_department.llm.router import ModelRouter
from ai_department.memory.port import MemorySection
from ai_department.runtime.session import AgentSession
from ai_department.tools.confirmations import GrantStore
from ai_department.tools.gateway import (
    Denied,
    Finished,
    GateContext,
    NeedsConfirmation,
    Ready,
    ToolGateway,
)

_RETRYABLE = frozenset({"timeout", "rate_limit", "unavailable"})


@dataclass(frozen=True)
class Pause:
    """Прогон ждёт подтверждения. Модель дальше не вызывается."""


@dataclass(frozen=True)
class Failure:
    """Прогон не может продолжиться."""

    reason: str
    message: str


@dataclass(frozen=True)
class Final:
    """Агент сформировал выход или упёрся в max_steps."""

    output: object


Stop = Pause | Failure | Final


class Runtime:
    """Цикл модели и инструментов для любой роли."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        gateway: ToolGateway,
        grants: GrantStore,
        max_provider_retries: int,
    ) -> None:
        self._router = router
        self._gateway = gateway
        self._grants = grants
        self._max_provider_retries = max_provider_retries

    def advance(self, session: AgentSession) -> Stop:
        """Идёт из Running до итога, паузы или сбоя."""
        if session.control.state is EmployeeState.WAITING_CONFIRMATION:
            return Pause()
        if session.control.state is not EmployeeState.RUNNING:
            return self._runtime_failure(session, "Цикл вызван не из Running")
        while session.control.state is EmployeeState.RUNNING:
            if session.steps >= session.task.constraints.max_steps:
                session.control.move(EmployeeState.EVALUATING, "max_steps")
                return Final(session.output if session.output is not None else {})
            outcome = self._model_step(session)
            if isinstance(outcome, Failure):
                return outcome
            if outcome.tool_calls:
                for call in outcome.tool_calls:
                    if session.steps >= session.task.constraints.max_steps:
                        session.control.move(EmployeeState.EVALUATING, "max_steps")
                        return Final(session.output if session.output is not None else {})
                    if session.control.state is not EmployeeState.RUNNING:
                        return Pause()
                    stop = self._tool_step(session, call)
                    if stop is not None:
                        return stop
                continue
            session.output = parse_output(outcome.text)
            session.control.move(EmployeeState.EVALUATING, "outcome")
            return Final(session.output)
        return self._runtime_failure(session, "Неожиданное состояние цикла")

    def apply_confirmation(self, session: AgentSession, decision: str) -> None:
        """Исполняет уже подтверждённый вызов или передаёт агенту denied."""
        pending = session.pending
        call = session.pending_call
        if pending is None or call is None:
            raise RuntimeError("Нет ожидающего инструмента")
        if decision == "reject":
            self._record_attempt(session, call, {"result": "denied"})
            session.pending = None
            session.pending_call = None
            return
        self._grants.add(session.log.run_id, pending.args_hash)
        prepared = self._gateway.prepare(call, self._context(session))
        if isinstance(prepared, Finished):
            self._record_tool(session, call, prepared)
            session.pending = None
            session.pending_call = None
            return
        if not isinstance(prepared, Ready):
            self._record_attempt(session, call, {"result": "denied"})
            session.pending = None
            session.pending_call = None
            return
        finished = self._gateway.invoke(prepared, call, self._context(session))
        self._record_tool(session, call, finished)
        session.pending = None
        session.pending_call = None

    def ignore_tool_while_waiting(self, session: AgentSession) -> bool:
        """Второй вызов в WaitingConfirmation не является подтверждением."""
        return session.control.state is EmployeeState.WAITING_CONFIRMATION

    def _model_step(self, session: AgentSession) -> LlmResponse | Failure:
        session.control.move(EmployeeState.WAITING_MODEL, "model_request")
        self._consume_step(session)
        requirements = session.requirements()
        try:
            entry = self._router.route(requirements, session.log)
        except NoModelError as exc:
            session.control.move(EmployeeState.FAILED, "no_model")
            return Failure("no_model", exc.message)
        attempt = 1
        while True:
            try:
                response = self._router.invoke(
                    entry,
                    session.request(),
                    session.log,
                    purpose=requirements.purpose,
                )
                break
            except ProviderError as exc:
                session.log.emit(
                    EventName.MODEL_FAILED,
                    "Вызов модели не удался",
                    {
                        "model_id": entry.model_id,
                        "kind": exc.kind,
                        "message": exc.message,
                        "attempt": attempt,
                    },
                    step=session.steps,
                )
                if exc.kind not in _RETRYABLE or attempt > self._max_provider_retries:
                    session.control.move(EmployeeState.FAILED, "provider")
                    return Failure(exc.kind, exc.message)
                attempt += 1
        session.control.move(EmployeeState.RUNNING, "model_response")
        session.model_calls += 1
        session.messages.append(_assistant(response))
        session.trace_steps.append(TraceStep(role_id=session.role_id, kind="model"))
        if response.text:
            session.output = parse_output(response.text)
        return response

    def _tool_step(self, session: AgentSession, call: ToolCall) -> Stop | None:
        if session.control.state is EmployeeState.WAITING_CONFIRMATION:
            return Pause()
        self._consume_step(session)
        prepared = self._gateway.prepare(call, self._context(session))
        if isinstance(prepared, Finished):
            self._record_tool(session, call, prepared)
            return None
        if isinstance(prepared, Denied):
            self._record_attempt(session, call, {"result": "denied", "rule": prepared.rule})
            return None
        if isinstance(prepared, NeedsConfirmation):
            session.pending = prepared.pending
            session.pending_call = call
            session.control.move(EmployeeState.WAITING_CONFIRMATION, "policy_confirm")
            return Pause()
        session.control.move(EmployeeState.WAITING_TOOL, "tool_call")
        finished = self._gateway.invoke(prepared, call, self._context(session))
        session.control.move(EmployeeState.RUNNING, "tool_result")
        self._record_tool(session, call, finished)
        return None

    def _record_attempt(self, session: AgentSession, call: ToolCall, result: object) -> None:
        """Отклонённая или запрещённая попытка: в трассе есть, обработчик не вызывался."""
        self._append_tool(session, call, result)
        session.trace_steps.append(
            TraceStep(role_id=session.role_id, kind="tool", tool_name=call.name, invoked=False)
        )

    def _record_tool(self, session: AgentSession, call: ToolCall, finished: Finished) -> None:
        self._append_tool(session, call, finished.result)
        session.trace_steps.append(
            TraceStep(
                role_id=session.role_id,
                kind="tool",
                tool_name=call.name,
                risk_level=finished.risk_level,
                invoked=finished.invoked,
                confirmation_consumed=finished.confirmation_consumed,
            )
        )
        session.memory.put(
            MemorySection.RUN,
            f"step-{session.steps}",
            {"tool": call.name, "ok": not finished.failed},
        )

    def _context(self, session: AgentSession) -> GateContext:
        return GateContext(
            run_id=session.log.run_id,
            role_id=session.role_id,
            bound_tools=session.bound_tools,
            role_ceiling=session.risk_ceiling,
            platform_ceiling=session.platform_ceiling,
            log=session.log,
            step=session.steps,
            expires_at=session.task.constraints.deadline,
        )

    def _consume_step(self, session: AgentSession) -> None:
        session.steps += 1

    def _append_tool(self, session: AgentSession, call: ToolCall, result: object) -> None:
        session.messages.append(
            ChatMessage(
                role="tool",
                content=json.dumps(result, ensure_ascii=False, default=str),
                tool_call_id=call.call_id,
            )
        )

    def _runtime_failure(self, session: AgentSession, message: str) -> Failure:
        if session.control.state is EmployeeState.RUNNING:
            session.control.move(EmployeeState.FAILED, "runtime")
        return Failure("runtime", message)


def parse_output(text: str) -> object:
    """Достаёт JSON-объект из ответа модели."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    loaded = _loads_object(stripped)
    if loaded is not None:
        return loaded
    embedded = _embedded_object(stripped)
    if embedded is not None:
        return embedded
    return {"_unparsed": text}


def _loads_object(text: str) -> object | None:
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded


def _embedded_object(text: str) -> dict[str, object] | None:
    decoder = json.JSONDecoder()
    start = 0
    while True:
        index = text.find("{", start)
        if index < 0:
            return None
        try:
            loaded, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            start = index + 1
            continue
        if isinstance(loaded, dict):
            return loaded
        start = index + 1


def _assistant(response: LlmResponse) -> ChatMessage:
    return ChatMessage(role="assistant", content=response.text, tool_calls=response.tool_calls)
