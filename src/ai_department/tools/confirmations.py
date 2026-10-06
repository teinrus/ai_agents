"""Одноразовые подтверждения и гранты на run_id + хеш аргументов."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ai_department.domain.errors import ConfirmationError


@dataclass(frozen=True)
class PendingConfirmation:
    """Запись ожидания. Хеш не уходит в ленту."""

    confirmation_id: str
    run_id: str
    tool: str
    arguments: dict[str, Any]
    args_hash: str
    call_id: str
    expires_at: datetime | None


class GrantStore:
    """Неиспользованные подтверждения. Повтор без нового гранта снова confirm."""

    def __init__(self) -> None:
        self._unused: set[tuple[str, str]] = set()

    def add(self, run_id: str, args_hash: str) -> None:
        self._unused.add((run_id, args_hash))

    def has(self, run_id: str, args_hash: str) -> bool:
        return (run_id, args_hash) in self._unused

    def consume(self, run_id: str, args_hash: str) -> bool:
        key = (run_id, args_hash)
        if key not in self._unused:
            return False
        self._unused.remove(key)
        return True


class ConfirmationBook:
    """Открытые ожидания. Повторный ответ на тот же id не проходит."""

    def __init__(self, ids: Callable[[], str]) -> None:
        self._ids = ids
        self._open: dict[str, PendingConfirmation] = {}

    def open(
        self,
        *,
        run_id: str,
        tool: str,
        arguments: dict[str, Any],
        args_hash: str,
        call_id: str,
        expires_at: datetime | None,
    ) -> PendingConfirmation:
        item = PendingConfirmation(
            confirmation_id=self._ids(),
            run_id=run_id,
            tool=tool,
            arguments=arguments,
            args_hash=args_hash,
            call_id=call_id,
            expires_at=expires_at,
        )
        self._open[item.confirmation_id] = item
        return item

    def take(self, confirmation_id: str, run_id: str) -> PendingConfirmation:
        item = self._open.get(confirmation_id)
        if item is None or item.run_id != run_id:
            raise ConfirmationError("Подтверждение не относится к этому прогону")
        del self._open[confirmation_id]
        return item
