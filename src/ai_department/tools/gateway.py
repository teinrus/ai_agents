"""Единственный путь к обработчику. Обхода decide в коде нет."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ai_department.domain.events import EventLog, EventName
from ai_department.domain.risk import RiskLevel
from ai_department.domain.states import PolicyDecision
from ai_department.domain.tools import ToolCall, ToolDefinition, insignificant_fields
from ai_department.events.redaction import redact
from ai_department.tools.confirmations import ConfirmationBook, GrantStore, PendingConfirmation
from ai_department.tools.hashing import args_hash
from ai_department.tools.policy import PolicyCall, PolicyContext, decide
from ai_department.tools.registry import ToolRegistry


@dataclass(frozen=True)
class GateContext:
    """Контекст вызова шлюза."""

    run_id: str
    role_id: str
    bound_tools: frozenset[str]
    role_ceiling: RiskLevel
    platform_ceiling: RiskLevel
    log: EventLog
    step: int
    expires_at: datetime | None


@dataclass(frozen=True)
class Denied:
    """Политика запретила вызов."""

    rule: int
    risk_level: RiskLevel


@dataclass(frozen=True)
class NeedsConfirmation:
    """Политика требует одноразовое подтверждение."""

    pending: PendingConfirmation
    risk_level: RiskLevel


@dataclass(frozen=True)
class Ready:
    """Политика разрешила вызов. Обработчик ещё не запускался."""

    definition: ToolDefinition | None
    risk_level: RiskLevel
    confirmation_consumed: bool


@dataclass(frozen=True)
class Finished:
    """Результат шага: ответ обработчика, его ошибка или отказ по схеме аргументов.

    `invoked` — обработчик вызывался; при отказе по схеме он не вызывался.
    """

    result: object
    risk_level: RiskLevel
    confirmation_consumed: bool
    failed: bool
    invoked: bool = True


class ToolGateway:
    """Политика, затем обработчик. Прямого вызова из агента нет."""

    def __init__(
        self,
        registry: ToolRegistry,
        grants: GrantStore,
        confirmations: ConfirmationBook,
    ) -> None:
        self._registry = registry
        self._grants = grants
        self._confirmations = confirmations

    def prepare(
        self, call: ToolCall, context: GateContext
    ) -> Finished | Denied | NeedsConfirmation | Ready:
        """Проверяет аргументы по схеме, затем применяет decide. Обработчик не вызывает."""
        definition = self._registry.get(call.name)
        risk = definition.risk_level if definition is not None else RiskLevel.READ
        if definition is not None and call.name in context.bound_tools:
            problem = _schema_problem(definition.parameters_schema, call.arguments)
            if problem is not None:
                context.log.emit(
                    EventName.TOOL_FAILED,
                    "Аргументы не по схеме",
                    {"tool": call.name, "kind": "arguments", "message": problem},
                    step=context.step,
                )
                return Finished(
                    result={
                        "error": "arguments",
                        "message": problem,
                        "hint": "Повтори вызов с исправленными аргументами",
                    },
                    risk_level=risk,
                    confirmation_consumed=False,
                    failed=True,
                    invoked=False,
                )
        digest = args_hash(
            call.arguments,
            insignificant_fields(definition) if definition is not None else frozenset(),
        )
        result = decide(
            PolicyCall(
                name=call.name,
                risk_level=risk,
                has_grant=self._grants.has(context.run_id, digest),
            ),
            PolicyContext(
                run_id=context.run_id,
                role_id=context.role_id,
                bound_tools=context.bound_tools,
                role_ceiling=context.role_ceiling,
                platform_ceiling=context.platform_ceiling,
            ),
        )
        safe = _safe_args(call.arguments)
        if result.decision is PolicyDecision.DENY:
            context.log.emit(
                EventName.TOOL_DENIED,
                "Инструмент запрещён",
                {"tool": call.name, "risk_level": risk.value, "rule": result.rule},
                step=context.step,
            )
            return Denied(rule=result.rule, risk_level=risk)
        if result.decision is PolicyDecision.CONFIRM:
            pending = self._confirmations.open(
                run_id=context.run_id,
                tool=call.name,
                arguments=dict(call.arguments),
                args_hash=digest,
                call_id=call.call_id,
                expires_at=context.expires_at,
            )
            context.log.emit(
                EventName.TOOL_CONFIRMATION_REQUIRED,
                "Нужно подтверждение",
                {"confirmation_id": pending.confirmation_id, "tool": call.name, "arguments": safe},
                step=context.step,
            )
            return NeedsConfirmation(pending=pending, risk_level=risk)
        if risk is RiskLevel.ACT and not self._grants.consume(context.run_id, digest):
            context.log.emit(
                EventName.TOOL_DENIED,
                "Подтверждение уже использовано",
                {"tool": call.name, "risk_level": risk.value, "rule": 5},
                step=context.step,
            )
            return Denied(rule=5, risk_level=risk)
        return Ready(
            definition=definition,
            risk_level=risk,
            confirmation_consumed=risk is RiskLevel.ACT,
        )

    def invoke(self, ready: Ready, call: ToolCall, context: GateContext) -> Finished:
        """Вызывает обработчик реестра. Ошибка шага не роняет прогон."""
        if ready.definition is None:
            message = "Обработчик не зарегистрирован"
            context.log.emit(
                EventName.TOOL_FAILED,
                "Инструмент вернул ошибку",
                {"tool": call.name, "kind": "handler", "message": message},
                step=context.step,
            )
            return Finished(
                result={"error": "handler", "message": message},
                risk_level=ready.risk_level,
                confirmation_consumed=ready.confirmation_consumed,
                failed=True,
            )
        try:
            produced = ready.definition.handler(call.arguments)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            context.log.emit(
                EventName.TOOL_FAILED,
                "Инструмент вернул ошибку",
                {"tool": call.name, "kind": "handler", "message": message},
                step=context.step,
            )
            return Finished(
                result={"error": "handler", "message": message},
                risk_level=ready.risk_level,
                confirmation_consumed=ready.confirmation_consumed,
                failed=True,
            )
        context.log.emit(
            EventName.TOOL_INVOKED,
            "Инструмент выполнен",
            {
                "tool": call.name,
                "risk_level": ready.risk_level.value,
                "arguments": _safe_args(call.arguments),
            },
            step=context.step,
        )
        return Finished(
            result=produced,
            risk_level=ready.risk_level,
            confirmation_consumed=ready.confirmation_consumed,
            failed=False,
        )


def _safe_args(arguments: dict[str, Any]) -> dict[str, Any]:
    cleaned = redact(arguments)
    if isinstance(cleaned, dict):
        return cleaned
    return {}


def _schema_problem(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Первая ошибка валидации или None. Некорректная схема роли — тоже ошибка шага."""
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(arguments), key=lambda item: str(list(item.path)))
    except SchemaError as exc:
        return f"Схема инструмента некорректна: {exc.message}"
    if not errors:
        return None
    first = errors[0]
    where = ".".join(str(part) for part in first.path)
    message = first.message
    if first.validator == "pattern":
        described = first.schema.get("description") if isinstance(first.schema, dict) else None
        if isinstance(described, str) and described:
            message = f"не подходит под формат: {described}"
    return f"{where}: {message}" if where else message
