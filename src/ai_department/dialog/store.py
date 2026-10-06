"""Порт и адаптеры хранилища тредов. Домен ролей сюда не входит."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from ai_department.domain.thread import ReplyKind, ThreadMessage, ThreadRecord, ThreadSummary

LAST_TEXT_LIMIT = 120


class ThreadStore(Protocol):
    """Сохранение, чтение и список сводок. Новые сверху."""

    def save(self, record: ThreadRecord) -> None:
        """Пишет тред целиком."""

    def load(self, thread_id: str) -> ThreadRecord | None:
        """Возвращает запись или None."""

    def list(self) -> list[ThreadSummary]:
        """Сводки по убыванию updated_at."""


def summary_of(record: ThreadRecord) -> ThreadSummary:
    """Сводка: число сообщений и обрезанный текст последнего."""
    last_text = record.messages[-1].text[:LAST_TEXT_LIMIT] if record.messages else ""
    return ThreadSummary(
        thread_id=record.thread_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        message_count=len(record.messages),
        last_text=last_text,
    )


def record_to_json(record: ThreadRecord) -> str:
    """JSON записи для тела SQLite и тестов без БД."""
    return json.dumps(
        {
            "thread_id": record.thread_id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "messages": [
                {
                    "author": item.author,
                    "text": item.text,
                    "run_id": item.run_id,
                    "kind": None if item.kind is None else item.kind.value,
                }
                for item in record.messages
            ],
            "run_ids": list(record.run_ids),
            "pending_run_id": record.pending_run_id,
        },
        ensure_ascii=False,
    )


def record_from_json(text: str) -> ThreadRecord:
    """Обратная разборка JSON записи."""
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("ожидался объект записи треда")
    messages: list[ThreadMessage] = []
    raw_messages = raw.get("messages")
    if isinstance(raw_messages, list):
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            kind_raw = item.get("kind")
            run_id = item.get("run_id")
            messages.append(
                ThreadMessage(
                    author=str(item.get("author", "")),
                    text=str(item.get("text", "")),
                    run_id=run_id if isinstance(run_id, str) else None,
                    kind=ReplyKind(kind_raw) if isinstance(kind_raw, str) else None,
                )
            )
    raw_ids = raw.get("run_ids")
    run_ids = tuple(str(item) for item in raw_ids) if isinstance(raw_ids, list) else ()
    pending = raw.get("pending_run_id")
    return ThreadRecord(
        thread_id=str(raw["thread_id"]),
        created_at=str(raw["created_at"]),
        updated_at=str(raw["updated_at"]),
        messages=tuple(messages),
        run_ids=run_ids,
        pending_run_id=pending if isinstance(pending, str) else None,
    )


class InMemoryThreadStore:
    """Адаптер в памяти процесса. Теряется при перезапуске."""

    def __init__(self) -> None:
        self._items: dict[str, ThreadRecord] = {}

    def save(self, record: ThreadRecord) -> None:
        self._items[record.thread_id] = record

    def load(self, thread_id: str) -> ThreadRecord | None:
        return self._items.get(thread_id)

    def list(self) -> list[ThreadSummary]:
        summaries = [summary_of(record) for record in self._items.values()]
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries


class SqliteThreadStore:
    """SQLite-адаптер: сводка без разбора тела JSON."""

    def __init__(self, path: str) -> None:
        parent = Path(path).parent
        if str(parent) not in {"", "."}:
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    body TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    last_text TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def save(self, record: ThreadRecord) -> None:
        summary = summary_of(record)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO threads (
                    thread_id, created_at, updated_at, body, message_count, last_text
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    body = excluded.body,
                    message_count = excluded.message_count,
                    last_text = excluded.last_text
                """,
                (
                    record.thread_id,
                    record.created_at,
                    record.updated_at,
                    record_to_json(record),
                    summary.message_count,
                    summary.last_text,
                ),
            )
            self._conn.commit()

    def load(self, thread_id: str) -> ThreadRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        body = row[0]
        if not isinstance(body, str):
            return None
        return record_from_json(body)

    def list(self) -> list[ThreadSummary]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT thread_id, created_at, updated_at, message_count, last_text
                FROM threads
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [
            ThreadSummary(
                thread_id=str(thread_id),
                created_at=str(created_at),
                updated_at=str(updated_at),
                message_count=int(message_count),
                last_text=str(last_text),
            )
            for thread_id, created_at, updated_at, message_count, last_text in rows
        ]
