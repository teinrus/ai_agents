"""Адрес ящика без сети."""

from roles.mail.mailbox import ImapSmtpMailbox, InMemoryMailbox


def test_in_memory_mailbox_default_address() -> None:
    assert InMemoryMailbox().address() == "employee@example.com"


def test_imap_mailbox_keeps_full_user() -> None:
    mailbox = ImapSmtpMailbox({"IMAP_USER": "me@yandex.ru", "IMAP_HOST": "imap.yandex.ru"})
    assert mailbox.address() == "me@yandex.ru"


def test_imap_mailbox_completes_user_from_host() -> None:
    mailbox = ImapSmtpMailbox({"IMAP_USER": "me", "IMAP_HOST": "imap.yandex.ru"})
    assert mailbox.address() == "me@yandex.ru"


def test_imap_mailbox_address_refuses_without_user() -> None:
    mailbox = ImapSmtpMailbox({})
    try:
        mailbox.address()
    except Exception as exc:
        assert getattr(exc, "variable", "") == "IMAP_USER"
    else:
        raise AssertionError("ожидался отказ без IMAP_USER")
