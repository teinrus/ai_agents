"""ASGI-вход для внешнего сервера. Панель монтируется так же, как в __main__."""

from __future__ import annotations

from ai_department.__main__ import load_local_env, mount_panel
from ai_department.composition import build_from_environment

load_local_env()
_department = build_from_environment()
mount_panel(_department.app)
app = _department.app
