"""Приём задачи, выбор роли и переводы состояний. Модель и инструменты не вызывает."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from ai_department.domain.automaton import automatic_idle, ensure_transition
from ai_department.domain.errors import ConfigError, ConfirmationError, RunNotFound, ValidationError
from ai_department.domain.evaluation import failed_remarks
from ai_department.domain.events import EventName
from ai_department.domain.risk import RiskLevel, exceeds
from ai_department.domain.role import RolePlugin
from ai_department.domain.run import PendingView, RunSnapshot
from ai_department.domain.states import EmployeeState, RunStatus, VerdictKind
from ai_department.domain.task import Task, constraints_payload
from ai_department.evaluation.service import EvaluationCycle
from ai_department.events.bus import EventBus, RunLogger
from ai_department.events.redaction import redact
from ai_department.memory.port import MemorySection, MemoryStore
from ai_department.memory.scoped import ScopedMemory
from ai_department.runtime.loop import Failure, Final, Pause, Runtime
from ai_department.runtime.session import AgentSession
from ai_department.tools.confirmations import ConfirmationBook
from ai_department.tools.registry import ToolRegistry


@dataclass
class Employee:
    """Экземпляр роли. Переживает прогоны и не удаляется."""

    role_id: str
    state: EmployeeState


@dataclass
class ActiveRun:
    """Прогон в памяти процесса."""

    run_id: str
    task: Task
    role_id: str | None = None
    status: RunStatus | None = None
    failure_reason: str | None = None
    output: object | None = None
    step_count: int = 0
    revision_count: int = 0
    pending: PendingView | None = None


class BoundControl:
    """Переходы одного сотрудника через таблицу оркестратора."""

    def __init__(self, orchestrator: Orchestrator, employee: Employee, log: RunLogger) -> None:
        self._orchestrator = orchestrator
        self._employee = employee
        self._log = log

    @property
    def state(self) -> EmployeeState:
        return self._employee.state

    def move(self, target: EmployeeState, reason: str) -> None:
        self._orchestrator.move(self._employee, target, reason, self._log)


class Orchestrator:
    """Реестр ролей и жизненный цикл прогона."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        evaluation: EvaluationCycle,
        tools: ToolRegistry,
        confirmations: ConfirmationBook,
        bus: EventBus,
        memory: MemoryStore,
        platform_ceiling: RiskLevel,
        role_threshold: float,
        clock: Callable[[], datetime],
    ) -> None:
        self._runtime = runtime
        self._evaluation = evaluation
        self._tools = tools
        self._confirmations = confirmations
        self._bus = bus
        self._memory = memory
        self._platform_ceiling = platform_ceiling
        self._role_threshold = role_threshold
        self._clock = clock
        self._plugins: list[RolePlugin] = []
        self._disabled: set[str] = set()
        self._employees: dict[str, Employee] = {}
        self._runs: dict[str, ActiveRun] = {}
        self._sessions: dict[str, AgentSession] = {}
        self._logs: dict[str, RunLogger] = {}

    def register(self, plugin: RolePlugin) -> None:
        """Принимает плагин из корня сборки и создаёт сотрудника."""
        if exceeds(plugin.risk_ceiling, self._platform_ceiling):
            raise ConfigError(
                "PLATFORM_RISK_CEILING",
                f"Потолок роли {plugin.role_id} выше платформенного",
            )
        if any(item.role_id == plugin.role_id for item in self._plugins):
            raise ValidationError(f"Роль {plugin.role_id} уже зарегистрирована")
        definitions = tuple(plugin.tools())
        known = {item.name for item in definitions}
        for skill in plugin.skills:
            if not set(skill.tool_names) <= known:
                raise ValidationError(f"Скилл {skill.skill_id} ссылается на неизвестный инструмент")
        for definition in definitions:
            self._tools.register(definition)
        self._plugins.append(plugin)
        employee = Employee(role_id=plugin.role_id, state=EmployeeState.REGISTERED)
        self._employees[plugin.role_id] = employee
        self.move(employee, EmployeeState.IDLE, "registered", self._platform_log())

    def disable(self, role_id: str) -> None:
        """Переводит свободного сотрудника роли в Retired."""
        self._disabled.add(role_id)
        employee = self._employees[role_id]
        if employee.state is not EmployeeState.IDLE:
            raise ConfigError("ENABLED_ROLES", "Роль занята и остаётся в текущем состоянии")
        self.move(employee, EmployeeState.RETIRED, "role_disabled", self._platform_log())

    def submit(self, task: Task) -> RunSnapshot:
        """Принимает задачу и ведёт прогон до паузы или терминального статуса."""
        if not task.correlation_id:
            task = replace(task, correlation_id=uuid4().hex)
        run_id = uuid4().hex
        record = ActiveRun(run_id=run_id, task=task)
        log = RunLogger(bus=self._bus, run_id=run_id, correlation_id=task.correlation_id)
        self._runs[run_id] = record
        self._logs[run_id] = log
        log.emit(
            EventName.TASK_RECEIVED,
            "Задача принята",
            {
                "goal": task.goal,
                "constraints": constraints_payload(task.constraints),
                "payload": task.payload,
            },
        )
        chosen = self._select(task)
        if chosen is None:
            record.status = RunStatus.NO_ROLE
            log.emit(
                EventName.TASK_FINISHED,
                "Роль не выбрана",
                {"status": RunStatus.NO_ROLE.value, "steps": 0, "revisions": 0},
            )
            return self.snapshot(run_id)
        plugin, score, rejected = chosen
        record.role_id = plugin.role_id
        log.role_id = plugin.role_id
        log.emit(
            EventName.AGENT_SELECTED,
            "Роль выбрана",
            {"role_id": plugin.role_id, "score": score, "rejected": rejected},
        )
        employee = self._employees[plugin.role_id]
        self.move(employee, EmployeeState.ASSIGNED, "selected", log)
        log.emit(
            EventName.SKILL_BOUND,
            "Скиллы привязаны",
            {"skills": [skill.skill_id for skill in plugin.skills]},
        )
        self.move(employee, EmployeeState.RUNNING, "started", log)
        session = AgentSession(
            task=task,
            role_id=plugin.role_id,
            skills=tuple(plugin.skills),
            output_schema=plugin.output_schema,
            risk_ceiling=plugin.risk_ceiling,
            platform_ceiling=self._platform_ceiling,
            tools={item.name: item for item in plugin.tools()},
            control=BoundControl(self, employee, log),
            log=log,
            memory=ScopedMemory(self._memory, run_id=run_id, role_id=plugin.role_id),
        )
        self._sessions[run_id] = session
        self._drive(record, session, log)
        return self.snapshot(run_id)

    def confirm(self, run_id: str, confirmation_id: str, decision: str) -> RunSnapshot:
        """approve выполняет инструмент, reject передаёт агенту denied."""
        record = self._require(run_id)
        session = self._sessions.get(run_id)
        log = self._logs.get(run_id)
        if session is None or log is None or record.role_id is None:
            raise ConfirmationError("Прогон не ожидает подтверждения")
        employee = self._employees[record.role_id]
        if employee.state is not EmployeeState.WAITING_CONFIRMATION:
            raise ConfirmationError("Прогон не ожидает подтверждения")
        pending = session.pending
        if pending is None or pending.confirmation_id != confirmation_id:
            raise ConfirmationError("Подтверждение не относится к этому прогону")
        self._confirmations.take(confirmation_id, run_id)
        if self._expired(record.task):
            self._fail_deadline(record, session, log)
            return self.snapshot(run_id)
        if decision not in {"approve", "reject"}:
            raise ConfirmationError("Ожидается approve или reject")
        self._runtime.apply_confirmation(session, decision)
        reason = "confirmation_approved" if decision == "approve" else "confirmation_rejected"
        session.control.move(EmployeeState.RUNNING, reason)
        record.pending = None
        self._drive(record, session, log)
        return self.snapshot(run_id)

    def ignore_unsolicited_tool(self, run_id: str) -> EmployeeState:
        """Вызов инструмента в WaitingConfirmation не меняет состояние и не подтверждает его."""
        record = self._require(run_id)
        session = self._sessions[run_id]
        if record.role_id is None or not self._runtime.ignore_tool_while_waiting(session):
            raise ConfirmationError("Прогон не ждёт подтверждения")
        return self._employees[record.role_id].state

    def snapshot(self, run_id: str) -> RunSnapshot:
        """Текущие поля прогона."""
        record = self._require(run_id)
        state = None if record.role_id is None else self._employees[record.role_id].state
        return RunSnapshot(
            run_id=record.run_id,
            correlation_id=record.task.correlation_id,
            status=record.status,
            state=state,
            role_id=record.role_id,
            failure_reason=record.failure_reason,
            pending_confirmation=record.pending,
            step_count=record.step_count,
            revision_count=record.revision_count,
            output=record.output,
        )

    def move(self, employee: Employee, target: EmployeeState, reason: str, log: RunLogger) -> None:
        """Применяет ребро контракта и публикует agent.state_changed."""
        ensure_transition(employee.state, target)
        source = employee.state
        employee.state = target
        log.emit(
            EventName.AGENT_STATE_CHANGED,
            "Состояние изменено",
            {"from": source.value, "to": target.value, "reason": reason},
            role_id=employee.role_id,
        )
        follow = automatic_idle(target)
        if follow is not None:
            self.move(employee, follow, "run_closed", log)

    def _drive(self, record: ActiveRun, session: AgentSession, log: RunLogger) -> None:
        while True:
            if session.control.state is EmployeeState.WAITING_CONFIRMATION:
                self._store_pending(record, session)
                if self._expired(record.task):
                    self._fail_deadline(record, session, log)
                return
            stop = self._runtime.advance(session)
            record.step_count = session.steps
            if isinstance(stop, Pause):
                self._store_pending(record, session)
                if self._expired(record.task):
                    self._fail_deadline(record, session, log)
                return
            if isinstance(stop, Failure):
                self._finish_failed(record, session, log, stop.reason, stop.message)
                return
            if self._evaluate(record, session, log, stop) == "revise":
                continue
            return

    def _evaluate(
        self, record: ActiveRun, session: AgentSession, log: RunLogger, stop: Final
    ) -> str:
        verdict = self._evaluation.run(
            record.task,
            stop.output,
            session.trace(),
            log,
            attempt=record.revision_count + 1,
        )
        record.step_count = session.steps
        if verdict.kind is VerdictKind.PASSED:
            record.status = RunStatus.COMPLETED
            record.output = stop.output
            record.pending = None
            session.control.move(EmployeeState.COMPLETED, "passed")
            self._remember(session, RunStatus.COMPLETED, stop.output)
            self._finish_event(log, record, None)
            return "done"
        if record.revision_count < record.task.constraints.max_revisions:
            record.revision_count += 1
            remaining = record.task.constraints.max_revisions - record.revision_count
            remarks = failed_remarks(verdict)
            log.emit(
                EventName.EVALUATION_REVISION_REQUESTED,
                "Нужна правка",
                {"remarks": remarks, "revisions_remaining": remaining},
            )
            session.control.move(EmployeeState.RUNNING, "revision")
            session.add_feedback(remarks)
            return "revise"
        record.status = RunStatus.REJECTED
        record.output = stop.output
        record.pending = None
        session.control.move(EmployeeState.FAILED, "revisions_exhausted")
        self._remember(session, RunStatus.REJECTED, stop.output)
        self._finish_event(log, record, None)
        return "done"

    def _finish_failed(
        self,
        record: ActiveRun,
        session: AgentSession,
        log: RunLogger,
        reason: str,
        message: str,
    ) -> None:
        record.status = RunStatus.FAILED
        record.failure_reason = reason
        record.step_count = session.steps
        record.pending = None
        self._remember(session, RunStatus.FAILED, None)
        self._finish_event(log, record, message)

    def _fail_deadline(self, record: ActiveRun, session: AgentSession, log: RunLogger) -> None:
        session.control.move(EmployeeState.FAILED, "deadline")
        self._finish_failed(record, session, log, "deadline", "Истёк deadline задачи")

    def _finish_event(self, log: RunLogger, record: ActiveRun, reason: str | None) -> None:
        status = record.status.value if record.status is not None else ""
        payload: dict[str, object] = {
            "status": status,
            "steps": record.step_count,
            "revisions": record.revision_count,
        }
        if record.status is RunStatus.FAILED and reason is not None:
            payload["reason"] = reason
        log.emit(EventName.TASK_FINISHED, "Прогон завершён", payload)

    def _remember(self, session: AgentSession, status: RunStatus, output: object) -> None:
        summary = ""
        if isinstance(output, dict):
            raw = output.get("summary")
            if isinstance(raw, str):
                summary = raw[:300]
        session.memory.put(
            MemorySection.RUN,
            "outcome",
            {"status": status.value, "summary": summary},
        )
        session.memory.put(MemorySection.AGENT, "last_run", {"status": status.value})

    def _store_pending(self, record: ActiveRun, session: AgentSession) -> None:
        pending = session.pending
        if pending is None:
            record.pending = None
            return
        safe = redact(pending.arguments)
        arguments = safe if isinstance(safe, dict) else {}
        record.pending = PendingView(
            confirmation_id=pending.confirmation_id,
            tool=pending.tool,
            arguments=arguments,
        )

    def _select(self, task: Task) -> tuple[RolePlugin, float, list[dict[str, object]]] | None:
        ranking: list[tuple[RolePlugin, float]] = []
        for plugin in self._plugins:
            if plugin.role_id in self._disabled:
                continue
            employee = self._employees.get(plugin.role_id)
            if employee is None or employee.state is not EmployeeState.IDLE:
                continue
            score = _score(plugin.score(task))
            if score is None:
                continue
            ranking.append((plugin, score))
        viable = [(plugin, score) for plugin, score in ranking if score >= self._role_threshold]
        if not viable:
            return None
        best = max(score for _, score in viable)
        chosen = next(plugin for plugin, score in viable if score == best)
        chosen_score = next(score for plugin, score in viable if plugin.role_id == chosen.role_id)
        rejected = [
            {"role_id": plugin.role_id, "score": score}
            for plugin, score in ranking
            if plugin.role_id != chosen.role_id
        ]
        return chosen, chosen_score, rejected

    def _expired(self, task: Task) -> bool:
        deadline = task.constraints.deadline
        return deadline is not None and self._clock() > deadline

    def _require(self, run_id: str) -> ActiveRun:
        record = self._runs.get(run_id)
        if record is None:
            raise RunNotFound(run_id)
        return record

    def _platform_log(self) -> RunLogger:
        return RunLogger(bus=self._bus, run_id="", correlation_id="platform")


def _score(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0 or number > 1 or number != number:
        return None
    return number
