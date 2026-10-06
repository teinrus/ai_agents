"""Два хранилища одного каталога видят одни и те же записи."""

from pathlib import Path

from ai_department.memory.port import MemorySection
from ai_department.memory.scoped import ScopedMemory
from ai_department.memory.shared import SharedDirectoryStore


def test_two_stores_share_agent_and_hide_foreign_run(tmp_path: Path) -> None:
    root = str(tmp_path / "shared")
    first = ScopedMemory(SharedDirectoryStore(root), run_id="run-1", role_id="records")
    second = ScopedMemory(SharedDirectoryStore(root), run_id="run-2", role_id="records")
    other_role = ScopedMemory(SharedDirectoryStore(root), run_id="run-3", role_id="mail")
    first.put(MemorySection.RUN, "outcome", {"summary": "один"})
    first.put(MemorySection.AGENT, "last_run", {"status": "completed"})
    assert second.get(MemorySection.RUN, "outcome") is None
    assert second.get(MemorySection.AGENT, "last_run") == {"status": "completed"}
    assert other_role.get(MemorySection.AGENT, "last_run") is None
