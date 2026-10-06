"""Канонический хеш существенных аргументов."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def args_hash(arguments: dict[str, Any], insignificant: frozenset[str]) -> str:
    """SHA-256 канонического JSON без несущественных полей."""
    filtered = {key: value for key, value in arguments.items() if key not in insignificant}
    canonical = json.dumps(
        filtered, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
