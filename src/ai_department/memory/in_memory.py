"""Память процесса для локального запуска."""

from __future__ import annotations


class InMemoryStore:
    """Словарь в процессе. Подпись порта от этого не меняется."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str], str] = {}

    def put(self, section: str, scope: str, key: str, value: str) -> None:
        self._rows[(section, scope, key)] = value

    def get(self, section: str, scope: str, key: str) -> str | None:
        return self._rows.get((section, scope, key))

    def items(self, section: str, scope: str) -> list[tuple[str, str]]:
        return [
            (key, value)
            for (row_section, row_scope, key), value in self._rows.items()
            if row_section == section and row_scope == scope
        ]
