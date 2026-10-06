"""Реестр описаний. Шлюз получает обработчик отсюда и плагин не импортирует."""

from __future__ import annotations

from ai_department.domain.tools import ToolDefinition


class ToolRegistry:
    """Имена инструментов уникальны в процессе."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Инструмент {definition.name} уже зарегистрирован")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)
