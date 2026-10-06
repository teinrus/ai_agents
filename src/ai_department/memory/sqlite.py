"""Первое сохраняемое хранилище. Смена backend не меняет сигнатуру порта."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SqliteStore:
    """SQLite-адаптер MemoryStore."""

    def __init__(self, path: str) -> None:
        parent = Path(path).parent
        if str(parent) not in {"", "."}:
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                section TEXT NOT NULL,
                scope TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (section, scope, key)
            )
            """
        )
        self._conn.commit()

    def put(self, section: str, scope: str, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO memory (section, scope, key, value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(section, scope, key) DO UPDATE SET value = excluded.value
            """,
            (section, scope, key, value),
        )
        self._conn.commit()

    def get(self, section: str, scope: str, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM memory WHERE section = ? AND scope = ? AND key = ?",
            (section, scope, key),
        ).fetchone()
        if row is None:
            return None
        value = row[0]
        return value if isinstance(value, str) else None

    def items(self, section: str, scope: str) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT key, value FROM memory WHERE section = ? AND scope = ?",
            (section, scope),
        ).fetchall()
        return [(str(key), str(value)) for key, value in rows]

    def close(self) -> None:
        """Закрывает соединение."""
        self._conn.close()
