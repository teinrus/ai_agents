"""Почтовая роль. Подключается корнем сборки и не импортируется ядром."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_department.domain.model import Capability, ModelRequirements, Preference
from ai_department.domain.risk import RiskLevel
from ai_department.domain.role import SkillSpec
from ai_department.domain.task import Task
from ai_department.domain.tools import ToolDefinition
from roles.mail.mailbox import Mailbox, build_mailbox

_OBJECT = "object"
_STRING = {"type": "string"}
_TEXT = {"type": "string", "minLength": 1}
_IMAP_ID = {
    "type": "string",
    "minLength": 1,
    "pattern": r"^[^\s<>\[\]]+$",
    "description": "id письма из результата list_unread, например 4828",
}
_ADDRESS = {
    "type": "string",
    "minLength": 3,
    "pattern": r"^(?:[^<>@]*<\s*)?[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+(?:\s*>)?$",
    "description": "Адрес вида user@domain.tld или Имя <user@domain.tld>",
}


def _address_schema(own: str) -> dict[str, object]:
    """Схема адреса с подсказкой про собственный ящик: модель видит её и в ошибке."""
    return {**_ADDRESS, "description": f"{_ADDRESS['description']}. Адрес этого ящика: {own}"}


def _handle_mailbox_instruction(address: str) -> str:
    """Справочник инструментов ящика: что вызывать и когда, одной строкой."""
    return (
        f"Ты ведёшь ящик {address}. "
        "Делай только то, что просит цель, лишних инструментов не вызывай. "
        "list_unread — только если цель про непрочитанные или новые письма или нужно найти письмо, "
        "на которое отвечать. "
        "read_message — перед ответом на письмо читать его целиком. "
        "create_draft — если цель просит черновик или ответ; in_reply_to равен id письма, "
        "тема начинается с «Re: ». "
        "send_message — только если цель прямо просит отправить; «мой адрес», «мне», «себе» "
        f"означают адрес ящика {address}. "
        "Не отвечать на автоматические уведомления и рассылки с адресов noreply, "
        "если цель не называет письмо прямо. "
        "summary — отчёт человеку: что сделано; "
        "для списка писем — сколько, от кого и о чём каждое; "
        "сделан ли черновик, а если нет — почему. "
        'Итог без черновика — {"summary": "..."}; '
        'с черновиком — {"summary": "...", "draft_id": ...}; '
        "draft_id указывать только строкой после create_draft."
    )


class MailRole:
    """Сотрудник ящика: чтение, черновик и отправка."""

    def __init__(self, mailbox: Mailbox) -> None:
        self._mailbox = mailbox
        self.role_id = "mail"
        self.description = (
            "Почтовый ящик: читает непрочитанные письма и открывает их целиком. "
            "Готовит черновики ответов и отправляет письма только с разрешения."
        )
        self.risk_ceiling = RiskLevel.ACT
        self.output_schema: dict[str, object] = {
            "type": _OBJECT,
            "additionalProperties": False,
            "required": ["summary"],
            "properties": {"summary": _STRING, "draft_id": {"type": ["string", "null"]}},
        }
        self.skills = (
            SkillSpec(
                skill_id="handle_mailbox",
                instruction=_handle_mailbox_instruction(mailbox.address()),
                tool_names=("list_unread", "read_message", "create_draft", "send_message"),
                requirements=ModelRequirements(
                    capabilities=frozenset({Capability.REASONING, Capability.TOOLS}),
                    preferences=(Preference.CHEAP, Preference.FAST),
                    min_context_window=2_000,
                    purpose="mailbox",
                ),
            ),
        )

    def score(self, task: Task) -> float:
        if task.payload.get("channel") == "mail":
            return 0.92
        channels = task.payload.get("channels")
        if isinstance(channels, list) and "mail" in channels:
            return 0.5
        return 0.0

    def tools(self) -> tuple[ToolDefinition, ...]:
        return (
            ToolDefinition(
                name="list_unread",
                description="Список непрочитанных писем: id, от кого, тема, дата, начало текста",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Сколько писем показать, целое число, обычно 10",
                        }
                    },
                    "required": ["limit"],
                },
                risk_level=RiskLevel.READ,
                handler=self._list_unread,
            ),
            ToolDefinition(
                name="read_message",
                description="Прочитать письмо целиком по id",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {"message_id": _IMAP_ID},
                    "required": ["message_id"],
                },
                risk_level=RiskLevel.READ,
                handler=self._read_message,
            ),
            ToolDefinition(
                name="create_draft",
                description="Сохранить черновик",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {
                        "to": _address_schema(self._mailbox.address()),
                        "subject": _TEXT,
                        "body": _TEXT,
                        "in_reply_to": _IMAP_ID,
                    },
                    "required": ["to", "subject", "body"],
                },
                risk_level=RiskLevel.DRAFT,
                handler=self._draft,
            ),
            ToolDefinition(
                name="send_message",
                description="Отправить письмо",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {
                        "to": _address_schema(self._mailbox.address()),
                        "subject": _TEXT,
                        "body": _TEXT,
                    },
                    "required": ["to", "subject", "body"],
                },
                risk_level=RiskLevel.ACT,
                handler=self._send,
            ),
        )

    def _list_unread(self, arguments: Mapping[str, Any]) -> object:
        return {"messages": self._mailbox.list_unread(_limit(arguments.get("limit", 10)))}

    def _read_message(self, arguments: Mapping[str, Any]) -> object:
        return self._mailbox.read_message(_text(arguments, "message_id"))

    def _draft(self, arguments: Mapping[str, Any]) -> object:
        draft_id = self._mailbox.save_draft(
            _text(arguments, "to"),
            _text(arguments, "subject"),
            _text(arguments, "body"),
            _optional_text(arguments, "in_reply_to"),
        )
        return {"draft_id": draft_id}

    def _send(self, arguments: Mapping[str, Any]) -> object:
        self._mailbox.send(
            _text(arguments, "to"),
            _text(arguments, "subject"),
            _text(arguments, "body"),
        )
        return {"sent": True}


def build_mail_role(env: Mapping[str, str] | None = None) -> MailRole:
    """Собирает роль. Секрет ящика нужен только живому обработчику."""
    return MailRole(build_mailbox(env or {}))


def _text(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ValueError(f"Поле {name} должно быть строкой")
    return value


def _limit(value: object) -> int:
    """Слабые модели передают число строкой: принимаем цифры в строке, остальное отвергаем."""
    if isinstance(value, bool):
        raise ValueError("Поле limit должно быть целым")
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value)
    if not isinstance(value, int) or value < 1:
        raise ValueError("Поле limit должно быть целым от 1")
    return value


def _optional_text(arguments: Mapping[str, Any], name: str) -> str | None:
    value = arguments.get(name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"Поле {name} должно быть строкой")
    return value
