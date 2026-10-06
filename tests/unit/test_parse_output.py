"""Разбор итога модели."""

from ai_department.runtime.loop import parse_output


def test_plain_object_is_returned() -> None:
    assert parse_output('{"summary": "два письма"}') == {"summary": "два письма"}


def test_object_inside_prose_is_extracted() -> None:
    text = 'Сводка готова.\n{"summary": "два письма", "draft_id": null}'
    assert parse_output(text) == {"summary": "два письма", "draft_id": None}


def test_prose_without_object_stays_unparsed() -> None:
    assert parse_output("просто текст") == {"_unparsed": "просто текст"}
