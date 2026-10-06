"""Порт памяти. Область раздела подставляет scoped-адаптер, не агент."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class MemorySection(StrEnum):
    """Три раздела платформы."""

    RUN = "run"
    AGENT = "agent"
    DEPARTMENT = "department"


@dataclass(frozen=True)
class MemoryRecord:
    """Запись, которую возвращает search."""

    key: str
    value: object


class MemoryBackend(Protocol):
    """put / get / search / list. Чужой run через этот порт не адресуется."""

    def put(self, section: MemorySection, key: str, value: object) -> None:
        """Пишет значение в раздел текущего контекста."""

    def get(self, section: MemorySection, key: str) -> object | None:
        """Читает значение или возвращает None."""

    def search(self, section: MemorySection, query: str) -> Sequence[MemoryRecord]:
        """Ищет подстроку по ключу и текстовому представлению значения."""

    def list(self, section: MemorySection, prefix: str) -> Sequence[str]:
        """Ключи раздела, начинающиеся с prefix."""


class MemoryStore(Protocol):
    """Общее хранилище. Область передаёт scoped-адаптер."""

    def put(self, section: str, scope: str, key: str, value: str) -> None:
        """Сохраняет JSON-строку."""

    def get(self, section: str, scope: str, key: str) -> str | None:
        """Возвращает JSON-строку или None."""

    def items(self, section: str, scope: str) -> list[tuple[str, str]]:
        """Пары ключ и JSON-строка в области."""
