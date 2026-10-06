"""Описание инструмента. Обработчик живёт в плагине, тип — в контракте."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ai_department.domain.risk import RiskLevel

ToolHandler = Callable[[Mapping[str, Any]], object]


@dataclass(frozen=True)
class ToolCall:
    """Запрос инструмента от модели."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolDefinition:
    """Описание, которое шлюз получает уже собранным."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    risk_level: RiskLevel
    handler: ToolHandler
    insignificant_fields: frozenset[str] = field(default_factory=frozenset)


def insignificant_fields(definition: ToolDefinition) -> frozenset[str]:
    """Поля схемы с x-insignificant не входят в хеш аргументов."""
    found: set[str] = set(definition.insignificant_fields)
    properties = definition.parameters_schema.get("properties")
    if isinstance(properties, dict):
        for name, schema in properties.items():
            if isinstance(schema, dict) and schema.get("x-insignificant") is True:
                found.add(str(name))
    return frozenset(found)
