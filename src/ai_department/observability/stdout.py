"""Подписчик stdout: одна JSON-строка на событие."""

from __future__ import annotations

import json

from ai_department.domain.events import Envelope, envelope_dict


def stdout_subscriber(event: Envelope) -> None:
    """Печатает конверт. Не участвует в решениях."""
    print(json.dumps(envelope_dict(event), ensure_ascii=False, separators=(",", ":")))
