"""Общий каталог файлов. Несколько процессов открывают один путь."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote


class SharedDirectoryStore:
    """Файлы раздела и области. Сигнатура MemoryStore прежняя."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def put(self, section: str, scope: str, key: str, value: str) -> None:
        path = self._path(section, scope, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def get(self, section: str, scope: str, key: str) -> str | None:
        path = self._path(section, scope, key)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def items(self, section: str, scope: str) -> list[tuple[str, str]]:
        directory = self._root / _segment(section) / _segment(scope)
        if not directory.is_dir():
            return []
        found: list[tuple[str, str]] = []
        for path in sorted(directory.glob("*.json")):
            found.append((unquote(path.stem), path.read_text(encoding="utf-8")))
        return found

    def _path(self, section: str, scope: str, key: str) -> Path:
        return self._root / _segment(section) / _segment(scope) / f"{_segment(key)}.json"


def _segment(value: str) -> str:
    return quote(value, safe="")
