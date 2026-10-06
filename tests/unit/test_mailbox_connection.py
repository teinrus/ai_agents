"""Повтор IMAP-соединения без сети."""

from __future__ import annotations

import imaplib
from email.message import EmailMessage
from typing import cast

import pytest

from roles.mail.mailbox import ImapSmtpMailbox

_PASSWORD = "secret-xyz"


class _FakeImap:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def login(self, user: str, password: str) -> str:
        del user, password
        return "OK"

    def select(self, mailbox: str) -> str:
        del mailbox
        return "OK"

    def search(self, charset: str | None, criteria: str) -> tuple[str, list[bytes]]:
        del charset, criteria
        return ("OK", [b"1"])

    def fetch(self, message_id: str, spec: str) -> tuple[str, list[object]]:
        del message_id, spec
        return ("OK", [(b"1 (BODY[] {n}", self._raw), b")"])

    def logout(self) -> str:
        return "BYE"

    def append(self, *args: object) -> str:
        del args
        return "OK"


def _letter() -> bytes:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "Тема живая"
    message.set_content("тело")
    return message.as_bytes()


def _env() -> dict[str, str]:
    return {
        "IMAP_HOST": "imap.example.test",
        "IMAP_USER": "user@example.test",
        "IMAP_PASSWORD": _PASSWORD,
    }


def test_list_unread_retries_after_capability_abort() -> None:
    raw = _letter()
    calls = {"n": 0}
    slept: list[float] = []

    def connector(host: str, port: int, timeout: float) -> imaplib.IMAP4_SSL:
        del host, port, timeout
        calls["n"] += 1
        if calls["n"] == 1:
            raise imaplib.IMAP4.abort("problems with connection")
        return cast(imaplib.IMAP4_SSL, _FakeImap(raw))

    mailbox = ImapSmtpMailbox(_env(), connector=connector, sleep=slept.append)
    found = mailbox.list_unread(5)
    assert slept == [1.5]
    assert found[0]["subject"] == "Тема живая"


def test_open_imap_gives_up_after_three_aborts() -> None:
    slept: list[float] = []

    def connector(host: str, port: int, timeout: float) -> imaplib.IMAP4_SSL:
        del host, port, timeout
        raise imaplib.IMAP4.abort("problems with connection")

    mailbox = ImapSmtpMailbox(_env(), connector=connector, sleep=slept.append)
    with pytest.raises(imaplib.IMAP4.abort):
        mailbox.list_unread(5)
    assert slept == [1.5, 3.0]


def test_auth_failure_is_not_retried_and_hides_password() -> None:
    slept: list[float] = []

    class _AuthFail(_FakeImap):
        def login(self, user: str, password: str) -> str:
            del user, password
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")

    def connector(host: str, port: int, timeout: float) -> imaplib.IMAP4_SSL:
        del host, port, timeout
        return cast(imaplib.IMAP4_SSL, _AuthFail(b""))

    mailbox = ImapSmtpMailbox(_env(), connector=connector, sleep=slept.append)
    with pytest.raises(imaplib.IMAP4.error) as caught:
        mailbox.list_unread(5)
    assert slept == []
    assert _PASSWORD not in str(caught.value)
