"""Хранилище тредов без сети: JSON, память и SQLite."""

from ai_department.dialog.store import (
    InMemoryThreadStore,
    SqliteThreadStore,
    record_from_json,
    record_to_json,
    summary_of,
)
from ai_department.domain.thread import ReplyKind, ThreadMessage, ThreadRecord


def _record(
    thread_id: str,
    updated_at: str,
    *,
    text: str | None = None,
    kind: ReplyKind | None = None,
) -> ThreadRecord:
    messages = ()
    if text is not None:
        messages = (ThreadMessage(author="assistant", text=text, kind=kind),)
    return ThreadRecord(
        thread_id=thread_id,
        created_at="2026-10-06T10:00:00+00:00",
        updated_at=updated_at,
        messages=messages,
        run_ids=("run-1",) if text else (),
        pending_run_id="run-1" if kind is ReplyKind.WAITING_CONFIRMATION else None,
    )


def test_json_round_trip_keeps_kind_and_empty_thread() -> None:
    waiting = _record(
        "t-1", "2026-10-06T10:01:00+00:00", text="ждите", kind=ReplyKind.WAITING_CONFIRMATION
    )
    restored = record_from_json(record_to_json(waiting))
    assert restored == waiting
    empty = _record("t-2", "2026-10-06T10:02:00+00:00")
    assert record_from_json(record_to_json(empty)).messages == ()
    assert record_from_json(record_to_json(empty)).pending_run_id is None


def test_summary_truncates_last_text() -> None:
    long = "я" * 200
    summary = summary_of(
        _record("t", "2026-10-06T10:01:00+00:00", text=long, kind=ReplyKind.ANSWER)
    )
    assert summary.message_count == 1
    assert summary.last_text == "я" * 120
    assert summary_of(_record("empty", "2026-10-06T10:00:00+00:00")).last_text == ""


def test_memory_list_is_newest_first() -> None:
    store = InMemoryThreadStore()
    store.save(_record("old", "2026-10-06T10:00:00+00:00"))
    store.save(_record("new", "2026-10-06T12:00:00+00:00", text="позже", kind=ReplyKind.ANSWER))
    listed = store.list()
    assert [item.thread_id for item in listed] == ["new", "old"]


def test_sqlite_store_is_visible_to_a_second_instance(tmp_path) -> None:
    path = tmp_path / "threads.db"
    first = SqliteThreadStore(str(path))
    first.save(_record("t", "2026-10-06T10:00:00+00:00", text="черновик", kind=ReplyKind.ANSWER))
    first.save(_record("t", "2026-10-06T11:00:00+00:00", text="готово", kind=ReplyKind.COMPLETED))
    second = SqliteThreadStore(str(path))
    loaded = second.load("t")
    assert loaded is not None
    assert loaded.updated_at == "2026-10-06T11:00:00+00:00"
    assert loaded.messages[-1].text == "готово"
    assert second.list()[0].message_count == 1
    assert second.list()[0].last_text == "готово"
    assert second.load("missing") is None
