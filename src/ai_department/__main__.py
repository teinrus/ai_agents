"""Локальный процесс на 127.0.0.1."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ai_department.composition import build_from_environment


def load_local_env(path: Path | None = None) -> None:
    """Подхватывает .env локального запуска. Уже заданное окружение не перетирает."""
    file = Path(".env") if path is None else path
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def mount_panel(app: FastAPI) -> None:
    """Отдаёт собранную панель с того же адреса, что и API."""
    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    index = dist / "index.html"
    assets = dist / "assets"
    if not index.is_file() or not assets.is_dir():
        return
    app.mount("/assets", StaticFiles(directory=assets), name="panel-assets")

    @app.get("/")
    def panel_index() -> FileResponse:
        return FileResponse(index)


def main() -> None:
    """Запускает API. Секреты читает корень сборки."""
    load_local_env()
    department = build_from_environment()
    mount_panel(department.app)
    uvicorn.run(department.app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
