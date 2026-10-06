"""Память, привязанная к run_id и role_id. Агент идентификаторы не передаёт."""

from __future__ import annotations

import json

from ai_department.domain.errors import MemoryAccessError
from ai_department.memory.port import MemoryRecord, MemorySection, MemoryStore


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class ScopedMemory:
    """Реализация порта для одного прогона."""

    def __init__(self, store: MemoryStore, *, run_id: str, role_id: str) -> None:
        self._store = store
        self._run_id = run_id
        self._role_id = role_id

    def put(self, section: MemorySection, key: str, value: object) -> None:
        self._store.put(section.value, self._scope(section), key, _dump(value))

    def get(self, section: MemorySection, key: str) -> object | None:
        raw = self._store.get(section.value, self._scope(section), key)
        if raw is None:
            return None
        loaded: object = json.loads(raw)
        return loaded

    def search(self, section: MemorySection, query: str) -> list[MemoryRecord]:
        found: list[MemoryRecord] = []
        for key, raw in self._store.items(section.value, self._scope(section)):
            if query in key or query in raw:
                loaded: object = json.loads(raw)
                found.append(MemoryRecord(key=key, value=loaded))
        return found

    def list(self, section: MemorySection, prefix: str) -> list[str]:
        return [
            key
            for key, _raw in self._store.items(section.value, self._scope(section))
            if key.startswith(prefix)
        ]

    def _scope(self, section: MemorySection) -> str:
        if section is MemorySection.RUN:
            return self._run_id
        if section is MemorySection.AGENT:
            return self._role_id
        if section is MemorySection.DEPARTMENT:
            return "platform"
        raise MemoryAccessError(f"Неизвестный раздел {section}")
