"""Роль clerk: чтение, черновик и фиксация заметки."""

from collections.abc import Mapping
from typing import Any

from ai_department.domain.model import Capability, ModelRequirements, Preference
from ai_department.domain.risk import RiskLevel
from ai_department.domain.role import SkillSpec
from ai_department.domain.task import Task
from ai_department.domain.tools import ToolDefinition

_OBJECT = "object"
_STRING = {"type": "string"}


class ClerkRole:
    """Сотрудник заметок. Нужен ядру, чтобы прогон шёл без почты."""

    def __init__(self) -> None:
        self.role_id = "clerk"
        self.description = "Заметки: читает, готовит черновик и фиксирует заметку."
        self.risk_ceiling = RiskLevel.ACT
        self.output_schema: dict[str, object] = {
            "type": _OBJECT,
            "additionalProperties": False,
            "required": ["summary"],
            "properties": {"summary": _STRING},
        }
        self.skills = (
            SkillSpec(
                skill_id="inspect",
                instruction="Прочитай заметку инструментом read_note, если нужен её текст.",
                tool_names=("read_note",),
                requirements=ModelRequirements(
                    capabilities=frozenset({Capability.REASONING, Capability.TOOLS}),
                    preferences=(Preference.CHEAP, Preference.FAST),
                    min_context_window=1_000,
                    purpose="inspect",
                ),
            ),
            SkillSpec(
                skill_id="publish",
                instruction="Черновик — draft_note. Фиксация — commit_note.",
                tool_names=("draft_note", "commit_note"),
                requirements=ModelRequirements(
                    capabilities=frozenset({Capability.CODING}),
                    preferences=(Preference.CHEAP,),
                    min_context_window=1_000,
                    purpose="publish",
                ),
            ),
        )
        self.notes: dict[str, str] = {}
        self.drafts: dict[str, str] = {}
        self.committed: list[str] = []

    def score(self, task: Task) -> float:
        if task.payload.get("role") == "clerk" or task.payload.get("channel") == "clerk":
            return 0.9
        return 0.0

    def tools(self) -> tuple[ToolDefinition, ...]:
        return (
            ToolDefinition(
                name="read_note",
                description="Прочитать заметку",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {"key": _STRING},
                    "required": ["key"],
                },
                risk_level=RiskLevel.READ,
                handler=self._read,
            ),
            ToolDefinition(
                name="draft_note",
                description="Сохранить черновик заметки",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {"key": _STRING, "text": _STRING},
                    "required": ["key", "text"],
                },
                risk_level=RiskLevel.DRAFT,
                handler=self._draft,
            ),
            ToolDefinition(
                name="commit_note",
                description="Зафиксировать заметку",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {
                        "key": _STRING,
                        "text": _STRING,
                        "trace_id": {"type": "string", "x-insignificant": True},
                    },
                    "required": ["key", "text"],
                },
                risk_level=RiskLevel.ACT,
                handler=self._commit,
                insignificant_fields=frozenset({"trace_id"}),
            ),
        )

    def _read(self, arguments: Mapping[str, Any]) -> object:
        key = _text(arguments, "key")
        return {"key": key, "text": self.notes.get(key, "")}

    def _draft(self, arguments: Mapping[str, Any]) -> object:
        key = _text(arguments, "key")
        text = _text(arguments, "text")
        self.drafts[key] = text
        return {"draft_id": key}

    def _commit(self, arguments: Mapping[str, Any]) -> object:
        key = _text(arguments, "key")
        text = _text(arguments, "text")
        self.notes[key] = text
        self.committed.append(key)
        return {"key": key}


def build_clerk_role(env: Mapping[str, str] | None = None) -> ClerkRole:
    """Собирает роль. Окружение ей не нужно."""
    del env
    return ClerkRole()


def _text(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ValueError(f"Поле {name} должно быть строкой")
    return value
