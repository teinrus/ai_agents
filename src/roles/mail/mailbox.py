"""Ящик почтовой роли. Ядро этот модуль не импортирует."""

from __future__ import annotations

import email
import email.policy
import html
import imaplib
import re
import smtplib
import socket
import ssl
import time
from collections.abc import Callable, Mapping
from email.message import EmailMessage, Message
from email.utils import formatdate, make_msgid
from typing import Protocol

ImapConnector = Callable[[str, int, float], imaplib.IMAP4_SSL]
"""Фабрика IMAP-клиента: хост, порт и таймаут в секундах."""

_SNIPPET_LIMIT = 200
_TEXT_LIMIT = 4000
_BLOCK_DROP = re.compile(
    r"<!--.*?-->|<(style|script|head)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_BREAK_TO_NEWLINE = re.compile(
    r"<br\s*/?>|</p>|</div>|</tr>|</li>|</h[1-6]>|</td>",
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<[^>]+>", re.DOTALL)
_SPACES = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_WHITESPACE = re.compile(r"\s+")


class MailboxConfigError(Exception):
    """Не хватает переменной ящика. В сообщение пароль не входит."""

    def __init__(self, variable: str) -> None:
        self.variable = variable
        super().__init__(f"Не задана переменная окружения {variable}")


class Mailbox(Protocol):
    """Операции ящика, которые вызывают обработчики роли."""

    def list_unread(self, limit: int) -> list[dict[str, object]]:
        """Непрочитанные письма: id, from, subject, date, snippet."""

    def read_message(self, message_id: str) -> dict[str, object]:
        """Письмо целиком по id. Флаг прочитанности не меняется."""

    def save_draft(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> str:
        """Сохраняет черновик и возвращает его идентификатор."""

    def send(self, recipient: str, subject: str, body: str) -> str:
        """Отправляет письмо. Вызов возможен только после шлюза."""

    def address(self) -> str:
        """Адрес этого ящика."""


class InMemoryMailbox:
    """Ящик процесса для прогона без внешней системы."""

    def __init__(self, address_value: str = "employee@example.com") -> None:
        self.address_value = address_value
        self.unread: list[dict[str, object]] = []
        self.drafts: list[dict[str, str]] = []
        self.sent: list[dict[str, str]] = []
        self.messages: dict[str, dict[str, object]] = {}

    def list_unread(self, limit: int) -> list[dict[str, object]]:
        return self.unread[:limit]

    def read_message(self, message_id: str) -> dict[str, object]:
        found = self.messages.get(message_id)
        if found is None:
            raise ValueError(f"Письмо {message_id} не найдено")
        return found

    def save_draft(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> str:
        draft_id = f"draft-{len(self.drafts) + 1}"
        draft = {"draft_id": draft_id, "to": recipient, "subject": subject, "body": body}
        if in_reply_to:
            draft["in_reply_to"] = in_reply_to
        self.drafts.append(draft)
        return draft_id

    def send(self, recipient: str, subject: str, body: str) -> str:
        self.sent.append({"to": recipient, "subject": subject, "body": body})
        return "sent"

    def address(self) -> str:
        """Адрес этого ящика."""
        return self.address_value


class ImapSmtpMailbox:
    """Живой ящик. Учётные данные читаются в момент вызова.

    Повтор соединения и пауза задаются снаружи, чтобы тесты не открывали сеть.
    """

    def __init__(
        self,
        env: Mapping[str, str],
        *,
        connector: ImapConnector | None = None,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = 3,
    ) -> None:
        self._env = env
        self._connector = connector if connector is not None else _ssl_imap
        self._sleep = sleep
        self._retries = retries

    def list_unread(self, limit: int) -> list[dict[str, object]]:
        client = self._open_imap()
        try:
            status, data = client.search(None, "UNSEEN")
            if status != "OK" or not data or not isinstance(data[0], bytes):
                return []
            found: list[dict[str, object]] = []
            for raw_id in data[0].split()[:limit]:
                message_id = raw_id.decode("ascii", errors="ignore")
                raw = self._peek(client, message_id)
                if not raw:
                    continue
                found.append(parse_summary(message_id, raw))
            return found
        finally:
            _logout(client)

    def read_message(self, message_id: str) -> dict[str, object]:
        client = self._open_imap()
        try:
            raw = self._peek(client, message_id)
            if not raw:
                raise ValueError(f"Письмо {message_id} не найдено")
            return parse_message(message_id, raw)
        finally:
            _logout(client)

    def save_draft(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> str:
        reply_header = ""
        client = self._open_imap()
        try:
            if in_reply_to:
                raw = self._peek(client, in_reply_to)
                if not raw:
                    raise ValueError(f"Письмо {in_reply_to} не найдено")
                reply_header = str(parse_message(in_reply_to, raw).get("message_id_header") or "")
            message = _message(
                self.address(), recipient, subject, body, in_reply_to_header=reply_header
            )
            client.append("Drafts", "", "", message.as_bytes())
            return f"draft-{subject}"
        finally:
            _logout(client)

    def send(self, recipient: str, subject: str, body: str) -> str:
        host = self._need("SMTP_HOST")
        user = self._env.get("SMTP_USER") or self._need("IMAP_USER")
        password = self._env.get("SMTP_PASSWORD") or self._need("IMAP_PASSWORD")
        port = _int_env(self._env, "SMTP_PORT", 465)
        timeout = _int_env(self._env, "SMTP_TIMEOUT", 20)
        message = _message(self.address(), recipient, subject, body)
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as client:
            client.login(user, password)
            client.send_message(message)
        return "sent"

    def _open_imap(self) -> imaplib.IMAP4_SSL:
        host = self._need("IMAP_HOST")
        user = self._need("IMAP_USER")
        password = self._need("IMAP_PASSWORD")
        port = _int_env(self._env, "IMAP_PORT", 993)
        timeout = float(_int_env(self._env, "IMAP_TIMEOUT", 20))
        last: BaseException | None = None
        attempts = max(self._retries, 1)
        for attempt in range(attempts):
            client: imaplib.IMAP4_SSL | None = None
            try:
                client = self._connector(host, port, timeout)
                client.login(user, password)
                client.select("INBOX")
                return client
            except Exception as exc:
                if client is not None:
                    _logout(client)
                if _is_auth_failure(exc):
                    raise
                if not _is_retryable(exc):
                    raise
                last = exc
            if attempt + 1 >= attempts:
                break
            self._sleep(1.5 * (2**attempt))
        if last is None:
            raise RuntimeError("Не удалось открыть IMAP")
        raise last

    def _peek(self, client: imaplib.IMAP4_SSL, message_id: str) -> bytes:
        if not message_id:
            return b""
        try:
            status, data = client.fetch(message_id, "(BODY.PEEK[])")
        except imaplib.IMAP4.error:
            return b""
        if status != "OK":
            try:
                status, data = client.fetch(message_id, "(RFC822)")
            except imaplib.IMAP4.error:
                return b""
        if status != "OK":
            return b""
        return _raw_from_fetch(data)

    def address(self) -> str:
        """Адрес этого ящика."""
        user = self._need("IMAP_USER")
        if "@" in user:
            return user
        host = self._env.get("IMAP_HOST") or ""
        if not host:
            return user
        domain = host[5:] if host.lower().startswith("imap.") else host
        return f"{user}@{domain}"

    def _need(self, name: str) -> str:
        value = self._env.get(name, "")
        if not value:
            raise MailboxConfigError(name)
        return value


def build_mailbox(env: Mapping[str, str]) -> Mailbox:
    """imap только если так сказано в окружении. Иначе ящик процесса."""
    if env.get("MAILBOX_BACKEND") == "imap":
        return ImapSmtpMailbox(env)
    return InMemoryMailbox()


def parse_summary(message_id: str, raw: bytes) -> dict[str, object]:
    """Краткая карточка письма: заголовки и обрезанный фрагмент тела."""
    message = _parse(raw)
    snippet = _WHITESPACE.sub(" ", _body_text(message)).strip()[:_SNIPPET_LIMIT]
    return {
        "id": message_id,
        "from": _header_str(message, "From"),
        "subject": _header_str(message, "Subject"),
        "date": _header_str(message, "Date"),
        "snippet": snippet,
    }


def parse_message(message_id: str, raw: bytes) -> dict[str, object]:
    """Полное письмо: заголовки и текстовое тело не длиннее лимита."""
    message = _parse(raw)
    return {
        "id": message_id,
        "from": _header_str(message, "From"),
        "to": _header_str(message, "To"),
        "subject": _header_str(message, "Subject"),
        "date": _header_str(message, "Date"),
        "message_id_header": _header_str(message, "Message-ID"),
        "text": _body_text(message)[:_TEXT_LIMIT],
    }


def _parse(raw: bytes) -> EmailMessage:
    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    if not isinstance(parsed, EmailMessage):
        message = EmailMessage()
        message.set_content("")
        return message
    return parsed


def _header_str(message: EmailMessage, name: str) -> str:
    value = message.get(name)
    if value is None:
        return ""
    return str(value).strip()


def _body_text(message: EmailMessage) -> str:
    body = message.get_body(preferencelist=("plain", "html"))
    if body is not None:
        return _part_as_text(body)
    plain = ""
    html_text = ""
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain" and not plain:
            plain = _part_as_text(part)
        elif content_type == "text/html" and not html_text:
            html_text = _part_as_text(part)
    return plain or html_text


def _part_as_text(part: Message) -> str:
    decoded = _decode_payload(part)
    if part.get_content_type() == "text/html":
        return _html_to_text(decoded)
    return _normalize_text(decoded)


def _decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    if not isinstance(payload, bytes):
        return str(payload)
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _html_to_text(source: str) -> str:
    """HTML в читаемый текст: без CSS/скриптов, с абзацами по блочным тегам."""
    without_blocks = _BLOCK_DROP.sub("", source)
    with_breaks = _BREAK_TO_NEWLINE.sub("\n", without_blocks)
    without_tags = _HTML_TAG.sub("", with_breaks)
    return _normalize_text(html.unescape(without_tags))


def _normalize_text(source: str) -> str:
    """Сжимает пробелы, сохраняет разрывы абзацев, убирает пустые строки."""
    collapsed = _SPACES.sub(" ", source.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.strip() for line in collapsed.split("\n")]
    nonempty = [line for line in lines if line]
    text = "\n".join(nonempty)
    return _MULTI_NEWLINE.sub("\n\n", text).strip()


def _message(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    *,
    in_reply_to_header: str = "",
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=_domain_of(sender))
    if in_reply_to_header:
        message["In-Reply-To"] = in_reply_to_header
        message["References"] = in_reply_to_header
    message.set_content(body)
    return message


def _domain_of(address: str) -> str | None:
    """Домен отправителя для Message-ID; без «@» оставляем домен хоста."""
    _, at, domain = address.rpartition("@")
    return domain.strip("<> ") or None if at else None


def _raw_from_fetch(payload: object) -> bytes:
    if not isinstance(payload, list):
        return b""
    for item in payload:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    return b""


def _ssl_imap(host: str, port: int, timeout: float) -> imaplib.IMAP4_SSL:
    return imaplib.IMAP4_SSL(host, port, timeout=timeout)


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _is_auth_failure(exc: BaseException) -> bool:
    if isinstance(exc, imaplib.IMAP4.abort):
        return False
    if not isinstance(exc, imaplib.IMAP4.error):
        return False
    text = str(exc).lower()
    return "authenticationfailed" in text or "invalid credentials" in text or "login" in text


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, imaplib.IMAP4.abort):
        return True
    if isinstance(exc, imaplib.IMAP4.error):
        return True
    return isinstance(exc, OSError | socket.timeout | ssl.SSLError)


def _logout(client: imaplib.IMAP4_SSL) -> None:
    try:
        client.logout()
    except imaplib.IMAP4.error:
        return
