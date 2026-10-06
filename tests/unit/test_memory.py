"""Изоляция разделов и SQLite-адаптер того же порта."""

import pytest

from ai_department.domain.errors import MemoryAccessError
from ai_department.memory.mock import MockMemory
from ai_department.memory.port import MemorySection
from ai_department.memory.scoped import ScopedMemory
from ai_department.memory.sqlite import SqliteStore


def test_runs_do_not_read_each_other_but_agent_section_is_shared() -> None:
    store = MockMemory()
    first = ScopedMemory(store, run_id="run-1", role_id="clerk")
    second = ScopedMemory(store, run_id="run-2", role_id="clerk")
    first.put(MemorySection.RUN, "outcome", {"summary": "один"})
    first.put(MemorySection.AGENT, "last_run", {"status": "completed"})
    assert second.get(MemorySection.RUN, "outcome") is None
    assert second.get(MemorySection.AGENT, "last_run") == {"status": "completed"}
    assert first.search(MemorySection.RUN, "один")[0].key == "outcome"
    assert first.list(MemorySection.RUN, "out") == ["outcome"]


def test_agent_sections_of_two_roles_are_isolated() -> None:
    store = MockMemory()
    clerk = ScopedMemory(store, run_id="run-1", role_id="clerk")
    mail = ScopedMemory(store, run_id="run-2", role_id="mail")
    clerk.put(MemorySection.AGENT, "last_run", {"status": "completed"})
    assert mail.get(MemorySection.AGENT, "last_run") is None


def test_unknown_section_is_rejected() -> None:
    memory = ScopedMemory(MockMemory(), run_id="run-1", role_id="clerk")
    with pytest.raises(MemoryAccessError):
        memory._scope(None)  # type: ignore[arg-type]


def test_sqlite_store_keeps_the_same_port(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "memory.db"
    store = SqliteStore(str(path))
    try:
        bound = ScopedMemory(store, run_id="run-1", role_id="clerk")
        bound.put(MemorySection.DEPARTMENT, "note", {"summary": "общий"})
        other = ScopedMemory(store, run_id="run-2", role_id="mail")
        assert other.get(MemorySection.DEPARTMENT, "note") == {"summary": "общий"}
        assert other.get(MemorySection.RUN, "note") is None
    finally:
        store.close()
