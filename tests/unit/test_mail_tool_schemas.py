"""Схемы аргументов почтовых инструментов без сети."""

from jsonschema import Draft202012Validator

from roles.mail.mailbox import InMemoryMailbox
from roles.mail.plugin import MailRole


def _schema(name: str) -> dict:
    role = MailRole(InMemoryMailbox())
    tool = next(t for t in role.tools() if t.name == name)
    return tool.parameters_schema


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(_schema(name))


def test_send_message_accepts_plain_and_named_addresses() -> None:
    validator = _validator("send_message")
    for to in (
        "a@b.ru",
        "Иван Петров <ivan@mail.ru>",
        '"Яндекс ID" <noreply@id.yandex.ru>',
    ):
        instance = {"to": to, "subject": "s", "body": "b"}
        assert validator.is_valid(instance), list(validator.iter_errors(instance))


def test_send_message_rejects_placeholder_and_empty_subject() -> None:
    validator = _validator("send_message")
    for to in ("[адрес получателя]", "<адрес>", "ivan", "ivan@localhost", ""):
        instance = {"to": to, "subject": "s", "body": "b"}
        assert not validator.is_valid(instance)
        assert list(validator.iter_errors(instance))
    empty_subject = {"to": "a@b.ru", "subject": "", "body": "b"}
    assert not validator.is_valid(empty_subject)
    assert list(validator.iter_errors(empty_subject))


def test_create_draft_in_reply_to_is_imap_uid() -> None:
    validator = _validator("create_draft")
    base = {"to": "a@b.ru", "subject": "s", "body": "b"}
    assert validator.is_valid(base), list(validator.iter_errors(base))
    with_id = {**base, "in_reply_to": "4828"}
    assert validator.is_valid(with_id), list(validator.iter_errors(with_id))
    for junk in ("<id из списка>", "4828 "):
        instance = {**base, "in_reply_to": junk}
        assert not validator.is_valid(instance)
        assert list(validator.iter_errors(instance))


def test_read_message_id_is_imap_uid() -> None:
    validator = _validator("read_message")
    ok = {"message_id": "4828"}
    assert validator.is_valid(ok), list(validator.iter_errors(ok))
    for junk in ("", "<id>"):
        instance = {"message_id": junk}
        assert not validator.is_valid(instance)
        assert list(validator.iter_errors(instance))


def test_list_unread_limit_must_be_integer() -> None:
    validator = _validator("list_unread")
    as_string = {"limit": "1"}
    assert not validator.is_valid(as_string)
    assert list(validator.iter_errors(as_string))
    as_int = {"limit": 1}
    assert validator.is_valid(as_int), list(validator.iter_errors(as_int))
