"""Разбор сырых RFC822 писем без сети."""

from __future__ import annotations

import base64
from email.message import EmailMessage

from roles.mail.mailbox import parse_message, parse_summary


def test_decodes_cyrillic_utf8_headers() -> None:
    message = EmailMessage()
    message["From"] = "Иван Петров <ivan@example.com>"
    message["To"] = "hr@example.com"
    message["Subject"] = "Вы на собеседование"
    message["Date"] = "Tue, 6 Oct 2026 21:00:00 +0300"
    message["Message-ID"] = "<utf8@example.com>"
    message.set_content("Короткий текст письма")
    raw = message.as_bytes()
    assert b"=?utf-8?" in raw.lower() or "Вы на собеседование".encode() in raw
    summary = parse_summary("11", raw)
    full = parse_message("11", raw)
    assert summary["from"] == "Иван Петров <ivan@example.com>"
    assert summary["subject"] == "Вы на собеседование"
    assert "Короткий" in str(summary["snippet"])
    assert full["text"].startswith("Короткий текст письма")


def test_handwritten_rfc2047_and_windows1251_body() -> None:
    subject = "=?utf-8?b?" + base64.b64encode("Тема на кириллице".encode()).decode("ascii") + "?="
    header = (
        "From: =?utf-8?b?"
        + base64.b64encode("Отдел кадров <hr@example.com>".encode()).decode("ascii")
        + "?=\r\n"
        "To: candidate@example.com\r\n"
        f"Subject: {subject}\r\n"
        "Date: Tue, 6 Oct 2026 21:00:00 +0300\r\n"
        "Message-ID: <raw@example.com>\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=windows-1251\r\n"
        "Content-Transfer-Encoding: 8bit\r\n"
        "\r\n"
    ).encode("ascii")
    raw = header + "Тело в windows-1251".encode("windows-1251")
    summary = parse_summary("7", raw)
    full = parse_message("7", raw)
    assert "Тема на кириллице" == summary["subject"]
    assert "Отдел кадров" in str(summary["from"])
    assert "Тело в windows-1251" in str(full["text"])
    assert full["message_id_header"] == "<raw@example.com>"


def test_koi8r_encoded_subject_is_readable() -> None:
    encoded = "=?koi8-r?b?" + base64.b64encode("Привет".encode("koi8-r")).decode("ascii") + "?="
    raw = (
        f"From: a@b.c\r\nSubject: {encoded}\r\nMIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nHi\r\n"
    ).encode("ascii")
    assert parse_summary("1", raw)["subject"] == "Привет"


def test_multipart_prefers_plain() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "mix"
    message.set_content("видимый plain")
    message.add_alternative("<p>html скрытый</p>", subtype="html")
    full = parse_message("2", message.as_bytes())
    assert "видимый plain" in str(full["text"])
    assert "html скрытый" not in str(full["text"])


def test_html_only_is_stripped_to_text() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "html"
    message.set_content("<html><body><p>Привет &amp; мир</p></body></html>", subtype="html")
    full = parse_message("3", message.as_bytes())
    text = str(full["text"])
    assert "Привет" in text
    assert "мир" in text
    assert "<p>" not in text
    assert "&amp;" not in text


def test_text_truncated_to_4000_chars() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "long"
    message.set_content("я" * 5000)
    full = parse_message("4", message.as_bytes())
    assert len(str(full["text"])) == 4000


def test_message_id_header_extracted() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "id"
    message["Message-ID"] = "<unique@example.com>"
    message.set_content("ok")
    full = parse_message("5", message.as_bytes())
    assert full["message_id_header"] == "<unique@example.com>"


def test_snippet_is_at_most_200_chars() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "snip"
    message.set_content(("слово " * 80).strip())
    summary = parse_summary("6", message.as_bytes())
    snippet = str(summary["snippet"])
    assert len(snippet) <= 200
    assert "  " not in snippet


def test_html_drops_css_and_keeps_paragraphs() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "css"
    message.set_content(
        "<html><head><style>body { margin:0 } #outlook a { padding:0; }</style></head>"
        "<body><p>Привет</p><p>Второй абзац</p></body></html>",
        subtype="html",
    )
    text = str(parse_message("8", message.as_bytes())["text"])
    assert "margin" not in text
    assert "padding" not in text
    assert text.startswith("Привет")
    assert "Второй абзац" in text.splitlines()


def test_html_br_becomes_newline() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "br"
    message.set_content("<p>раз<br>два</p>", subtype="html")
    assert str(parse_message("9", message.as_bytes())["text"]).splitlines() == ["раз", "два"]


def test_html_comment_is_removed() -> None:
    message = EmailMessage()
    message["From"] = "a@b.c"
    message["Subject"] = "comment"
    message.set_content("<!-- скрытый CSS body { margin:0 } --><p>Видно</p>", subtype="html")
    text = str(parse_message("10", message.as_bytes())["text"])
    assert text.startswith("Видно")
    assert "скрытый" not in text
    assert "margin" not in text


def test_outgoing_message_carries_date_message_id_and_threading() -> None:
    from roles.mail.mailbox import _message

    message = _message(
        "me@example.com", "you@example.com", "Re: тема", "текст", in_reply_to_header="<abc@x>"
    )
    assert message["Date"]
    assert message["Message-ID"].endswith("@example.com>")
    assert message["In-Reply-To"] == "<abc@x>"
    assert message["References"] == "<abc@x>"
    plain = _message("me", "you@example.com", "s", "b")
    assert plain["Message-ID"].startswith("<") and plain["In-Reply-To"] is None
