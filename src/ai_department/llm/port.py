"""Запрос и ответ порта провайдера. Типы SDK наружу не выходят."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ai_department.domain.tools import ToolCall


@dataclass(frozen=True)
class ToolSchema:
    """Описание инструмента, которое видит модель."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    """Сообщение диалога шага."""

    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LlmRequest:
    """Запрос complete: сообщения и инструменты. Требования маршрута сюда не входят.

    `temperature` — единственный параметр генерации; `None` оставляет умолчание провайдера.
    """

    messages: tuple[ChatMessage, ...]
    tools: tuple[ToolSchema, ...]
    temperature: float | None = None

    def __post_init__(self) -> None:
        if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature должна быть в диапазоне 0..2")


@dataclass(frozen=True)
class LlmResponse:
    """Текст и запрошенные tool-calls."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    token_count: int | None = None


class LlmProvider(Protocol):
    """Один вызов модели. Провайдер не ранжирует и не публикует маршрут."""

    def complete(self, provider_model_name: str, request: LlmRequest) -> LlmResponse:
        """Выполняет запрос к модели провайдера."""
