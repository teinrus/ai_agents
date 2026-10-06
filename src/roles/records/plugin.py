"""Роль учёта записей. Подключается корнем сборки и не импортируется ядром."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_department.domain.model import Capability, ModelRequirements, Preference
from ai_department.domain.risk import RiskLevel
from ai_department.domain.role import SkillSpec
from ai_department.domain.task import Task
from ai_department.domain.tools import ToolDefinition

_OBJECT = "object"
_STRING = {"type": "string"}


class RecordsRole:
    """Сотрудник картотеки: чтение списка и черновик записи."""

    def __init__(self) -> None:
        self.role_id = "records"
        self.description = "Картотека: показывает список записей и сохраняет черновик новой записи."
        self.risk_ceiling = RiskLevel.DRAFT
        self.output_schema: dict[str, object] = {
            "type": _OBJECT,
            "additionalProperties": False,
            "required": ["summary"],
            "properties": {"summary": _STRING, "record_id": _STRING},
        }
        self.skills = (
            SkillSpec(
                skill_id="keep_records",
                instruction=(
                    "Список записей читай через list_records. "
                    "Новую запись сохраняй через write_record."
                ),
                tool_names=("list_records", "write_record"),
                requirements=ModelRequirements(
                    capabilities=frozenset({Capability.REASONING, Capability.TOOLS}),
                    preferences=(Preference.CHEAP, Preference.FAST),
                    min_context_window=2_000,
                    purpose="records",
                ),
            ),
        )
        self.records: list[dict[str, str]] = []

    def score(self, task: Task) -> float:
        if task.payload.get("channel") == "records":
            return 0.75
        channels = task.payload.get("channels")
        if isinstance(channels, list) and "records" in channels:
            return 0.75
        return 0.0

    def tools(self) -> tuple[ToolDefinition, ...]:
        return (
            ToolDefinition(
                name="list_records",
                description="Список записей картотеки",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {"limit": {"type": "integer"}},
                    "required": ["limit"],
                },
                risk_level=RiskLevel.READ,
                handler=self._list,
            ),
            ToolDefinition(
                name="write_record",
                description="Сохранить черновик записи",
                parameters_schema={
                    "type": _OBJECT,
                    "properties": {"title": _STRING, "body": _STRING},
                    "required": ["title", "body"],
                },
                risk_level=RiskLevel.DRAFT,
                handler=self._write,
            ),
        )

    def _list(self, arguments: Mapping[str, Any]) -> object:
        limit = arguments.get("limit", 10)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("Поле limit должно быть целым")
        return {"records": self.records[:limit]}

    def _write(self, arguments: Mapping[str, Any]) -> object:
        title = _text(arguments, "title")
        body = _text(arguments, "body")
        record_id = f"record-{len(self.records) + 1}"
        self.records.append({"record_id": record_id, "title": title, "body": body})
        return {"record_id": record_id}


def build_records_role(env: Mapping[str, str] | None = None) -> RecordsRole:
    """Собирает роль. Секретов ей не нужно."""
    del env
    return RecordsRole()


def _text(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ValueError(f"Поле {name} должно быть строкой")
    return value
