"""Разбор сообщения клиента. Один вызов роутера, имя модели неизвестно."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ai_department.domain.errors import NoModelError, ProviderError
from ai_department.domain.events import EventLog
from ai_department.domain.model import Capability, ModelEntry, ModelRequirements, Preference
from ai_department.domain.thread import ThreadMessage
from ai_department.domain.tools import ToolCall
from ai_department.llm.port import ChatMessage, LlmRequest, ToolSchema
from ai_department.llm.router import ModelRouter
from ai_department.runtime.loop import parse_output

INTAKE_REQUIREMENTS = ModelRequirements(
    capabilities=frozenset({Capability.REASONING, Capability.TOOLS}),
    preferences=(Preference.CHEAP, Preference.FAST),
    min_context_window=4_000,
    purpose="intake",
)

DISPATCH_OPTION = "dispatch"
REPLY_OPTION = "reply"

_GOAL_HINT = "Что именно сделать: повтори просьбу человека, учитывая историю диалога"
_GENERIC_GOALS = frozenset(
    {
        "...",
        "goal",
        "задача",
        "просьба человека",
        "просьба человека своими словами",
        _GOAL_HINT.lower(),
    }
)


def _looks_like_broken_call(text: str) -> bool:
    """Обрывок JSON или вызова: такое клиенту не показывают."""
    head = text.lstrip("`").lstrip()
    if head.lower().startswith("json"):
        head = head[4:].lstrip()
    return head.startswith(("{", "[")) or '"function"' in text or "<tool_call" in text


def _degenerate_goal(goal: str) -> bool:
    """Пустая, шаблонная или скопированная из подсказки формулировка."""
    lowered = goal.strip().strip("<>«»\"'").lower()
    if len(lowered) < 4:
        return True
    if lowered in _GENERIC_GOALS:
        return True
    return lowered.startswith("<") or "своими словами" in lowered


_EMPTY_REPLY = "Не понял сообщение. Сформулируйте задачу или вопрос."


@dataclass(frozen=True)
class RoleCard:
    """Что приёмная знает о роли: идентификатор и описание."""

    role_id: str
    description: str


@dataclass(frozen=True)
class Dispatch:
    """Решение передать задачу сотруднику."""

    role_id: str
    goal: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Reply:
    """Решение ответить клиенту без прогона."""

    text: str


@dataclass(frozen=True)
class IntakeFailure:
    """Модель приёмной недоступна."""

    reason: str
    message: str


Decision = Dispatch | Reply


def parse_decision(text: str) -> Decision:
    """Читает решение модели.

    Обычный текст — ответ клиенту этим текстом. JSON-объект без допустимого
    решения — ответ-заглушка с просьбой уточнить, сырой JSON клиенту не уходит.
    """
    stripped = text.strip()
    if not stripped:
        return Reply(_EMPTY_REPLY)
    loaded = parse_output(stripped)
    if not isinstance(loaded, dict) or "_unparsed" in loaded:
        return Reply(_EMPTY_REPLY if _looks_like_broken_call(stripped) else stripped)
    action = loaded.get("action")
    if action == "dispatch":
        role_id = loaded.get("role_id")
        goal = loaded.get("goal")
        if isinstance(role_id, str) and role_id and isinstance(goal, str) and goal.strip():
            payload = loaded.get("payload")
            return Dispatch(
                role_id=role_id,
                goal=goal.strip(),
                payload=dict(payload) if isinstance(payload, dict) else {},
            )
    if action == "reply":
        reply = loaded.get("text")
        if isinstance(reply, str) and reply.strip():
            return Reply(reply.strip())
    return Reply(_EMPTY_REPLY)


def decision_from_calls(calls: Sequence[ToolCall]) -> Decision | None:
    """Решение из структурированного вызова: вариант dispatch или reply."""
    for call in calls:
        arguments = call.arguments
        if call.name == DISPATCH_OPTION:
            role_id = arguments.get("role_id")
            goal = arguments.get("goal")
            if isinstance(role_id, str) and role_id and isinstance(goal, str) and goal.strip():
                return Dispatch(role_id=role_id.strip(), goal=goal.strip())
        if call.name == REPLY_OPTION:
            text = arguments.get("text")
            if isinstance(text, str) and text.strip():
                return Reply(text.strip())
    return None


class Intake:
    """Шаг приёмной: история треда и карточки ролей на входе, решение на выходе."""

    def __init__(self, router: ModelRouter, roles: Sequence[RoleCard], history_limit: int) -> None:
        self._router = router
        self._roles = tuple(roles)
        self._history_limit = max(1, history_limit)

    def decide(self, history: Sequence[ThreadMessage], log: EventLog) -> Decision | IntakeFailure:
        """Публикует model.routed и model.called с пустым run_id."""
        request = LlmRequest(
            messages=self._messages(history), tools=self._options(), temperature=0.0
        )
        try:
            entry = self._router.route(INTAKE_REQUIREMENTS, log)
            decision = self._ask(entry, request, log)
            if decision == Reply(_EMPTY_REPLY):
                decision = self._ask(entry, request, log)
        except NoModelError as exc:
            return IntakeFailure("no_model", exc.message)
        except ProviderError as exc:
            return IntakeFailure(exc.kind, exc.message)
        latest = history[-1].text if history else ""
        return self._normalize(decision, latest)

    def _ask(self, entry: ModelEntry, request: LlmRequest, log: EventLog) -> Decision:
        response = self._router.invoke(entry, request, log, purpose=INTAKE_REQUIREMENTS.purpose)
        decision = decision_from_calls(response.tool_calls)
        return decision if decision is not None else parse_decision(response.text)

    def _normalize(self, decision: Decision, request: str) -> Decision:
        """Чинит типовые сбои слабых моделей: role_id вне списка и вырожденный goal."""
        if not isinstance(decision, Dispatch):
            return decision
        known = {card.role_id for card in self._roles}
        role_id = decision.role_id.strip("<>«» ")
        if role_id not in known and len(self._roles) == 1:
            role_id = self._roles[0].role_id
        goal = decision.goal
        if _degenerate_goal(goal) and request.strip():
            goal = request.strip()
        return Dispatch(role_id=role_id, goal=goal, payload=decision.payload)

    def _messages(self, history: Sequence[ThreadMessage]) -> tuple[ChatMessage, ...]:
        recent = list(history)[-self._history_limit :]
        chat = [ChatMessage(role="system", content=self._system())]
        for item in recent:
            role = "assistant" if item.author == "assistant" else "user"
            chat.append(ChatMessage(role=role, content=item.text))
        return tuple(chat)

    def _options(self) -> tuple[ToolSchema, ...]:
        role_ids = [card.role_id for card in self._roles]
        role_schema: dict[str, Any] = {"type": "string"}
        if role_ids:
            role_schema["enum"] = role_ids
        return (
            ToolSchema(
                name=DISPATCH_OPTION,
                description="Передать задачу сотруднику. Выбирай всегда, когда человек просит "
                "что-то сделать и в списке есть подходящий сотрудник.",
                parameters={
                    "type": "object",
                    "properties": {
                        "role_id": role_schema,
                        "goal": {"type": "string", "description": _GOAL_HINT},
                    },
                    "required": ["role_id", "goal"],
                },
            ),
            ToolSchema(
                name=REPLY_OPTION,
                description="Ответить человеку самому: приветствие, вопрос о возможностях, "
                "сообщение не по делу или задача, под которую нет сотрудника.",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            ),
        )

    def _system(self) -> str:
        if self._roles:
            cards = "\n".join(f"- {card.role_id}: {card.description}" for card in self._roles)
            example_role = self._roles[0].role_id
        else:
            cards = "- (сотрудников нет)"
            example_role = "role"
        return (
            "Ты приёмная департамента цифровых сотрудников. Сам задачи не выполняешь "
            "и не видишь данных сотрудников — ни писем, ни документов: "
            "ты либо передаёшь задачу сотруднику, либо коротко отвечаешь человеку.\n"
            f"Сотрудники:\n{cards}\n\n"
            f"Если человек просит что-то сделать или спрашивает о том, что знает только "
            f"сотрудник (есть ли письма, что нового, что написал кто-то), — вызови "
            f"{DISPATCH_OPTION} с его role_id и просьбой человека своими словами. "
            "Не проси уточнений, если сотрудник может начать работу сам. "
            "Не обещай сделать что-то сам и никогда не придумывай ответ за сотрудника.\n"
            f"Если это приветствие, вопрос «что ты умеешь», сообщение не по делу или задача "
            f"не для наших сотрудников — вызови {REPLY_OPTION} с коротким ответом.\n"
            "Если вызов недоступен, верни один JSON без пояснений: "
            f'{{"action": "dispatch", "role_id": "{example_role}", "goal": "..."}} '
            'или {"action": "reply", "text": "..."}.'
        )
