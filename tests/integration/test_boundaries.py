"""Границы ядра: почта не протекает в платформу."""

from pathlib import Path

CORE = (
    "orchestrator",
    "runtime",
    "evaluation",
    "memory",
    "tools",
    "llm",
    "events",
    "observability",
    "dialog",
    "api",
    "domain",
)
FORBIDDEN = ("mail", "imap", "smtp")


def test_core_does_not_mention_mailbox_or_import_role_plugins() -> None:
    root = Path("src/ai_department")
    for package in CORE:
        for path in (root / package).rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for word in FORBIDDEN:
                assert word not in text, f"{path} содержит {word}"
            assert "import roles" not in text
            assert "from roles" not in text


def test_dialog_does_not_name_roles() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("src/ai_department/dialog").rglob("*.py")
    )
    for word in ("records", "clerk", "model_id", "openai"):
        assert word not in text, word


def test_mail_plugin_does_not_name_provider_sdk() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in Path("src/roles/mail").rglob("*.py")
    )
    for word in ("model_id", "openai", "anthropic"):
        assert word not in text


def test_records_plugin_stays_outside_mail_and_provider_sdk() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in Path("src/roles/records").rglob("*.py")
    )
    for word in ("mail", "imap", "smtp", "model_id", "openai", "anthropic"):
        assert word not in text, word
