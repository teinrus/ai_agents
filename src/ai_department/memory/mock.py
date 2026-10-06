"""Память тестов: то же хранилище и журнал операций."""

from __future__ import annotations

from ai_department.memory.in_memory import InMemoryStore


class MockMemory(InMemoryStore):
    """InMemory с журналом вызовов. Сеть не открывает."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str, str]] = []

    def put(self, section: str, scope: str, key: str, value: str) -> None:
        self.calls.append(("put", section, key))
        super().put(section, scope, key, value)

    def get(self, section: str, scope: str, key: str) -> str | None:
        self.calls.append(("get", section, key))
        return super().get(section, scope, key)
