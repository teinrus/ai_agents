"""Внешний журнал конвертов. Публикатор шины этот модуль не импортирует."""

from __future__ import annotations

import json
from pathlib import Path

from ai_department.domain.events import Envelope, EventLevel, envelope_dict


class FileBroker:
    """Дописывает конверт строкой JSON. Чтение сортирует по run_id и seq."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def publish(self, event: Envelope) -> None:
        """Один конверт, уже пронумерованный шиной."""
        if not event.run_id:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(envelope_dict(event), ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def read(self) -> list[Envelope]:
        """Все конверты журнала в порядке run_id, затем seq."""
        if not self._path.is_file():
            return []
        found: list[Envelope] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if isinstance(raw, dict):
                found.append(_envelope(raw))
        found.sort(key=lambda item: (item.run_id, item.seq))
        return found


def _envelope(raw: dict[str, object]) -> Envelope:
    role_id = raw.get("role_id")
    step = raw.get("step")
    payload = raw.get("payload")
    return Envelope(
        ts=str(raw.get("ts", "")),
        seq=int(str(raw.get("seq", "0"))),
        level=EventLevel(str(raw.get("level", "INFO"))),
        correlation_id=str(raw.get("correlation_id", "")),
        run_id=str(raw.get("run_id", "")),
        event=str(raw.get("event", "")),
        role_id=role_id if isinstance(role_id, str) else None,
        step=step if isinstance(step, int) else None,
        message=str(raw.get("message", "")),
        payload=payload if isinstance(payload, dict) else {},
    )
