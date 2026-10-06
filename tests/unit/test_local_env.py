"""Локальный .env не перетирает уже заданные переменные процесса."""

import os
from pathlib import Path

from ai_department.__main__ import load_local_env


def test_load_local_env_sets_missing_and_keeps_existing(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "MAILBOX_BACKEND=imap",
                "IMAP_HOST=imap.example.test",
                "ALREADY_SET=from-file",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ALREADY_SET", "from-process")
    monkeypatch.delenv("MAILBOX_BACKEND", raising=False)
    monkeypatch.delenv("IMAP_HOST", raising=False)
    load_local_env(env_file)
    assert os.environ["MAILBOX_BACKEND"] == "imap"
    assert os.environ["IMAP_HOST"] == "imap.example.test"
    assert os.environ["ALREADY_SET"] == "from-process"
