import pytest

from app.jsonparse import NotJSON, extract_json


def test_plain_json():
    assert extract_json('{"reply": "ok"}') == {"reply": "ok"}


def test_strips_thinking_and_fences():
    raw = '```json\n<think>ragiono</think>\n{"reply": "ok"}\n```'
    assert extract_json(raw)["reply"] == "ok"


def test_finds_object_surrounded_by_text():
    assert extract_json('ecco: {"a": 1} fine') == {"a": 1}


def test_rejects_missing_or_array_json():
    with pytest.raises(NotJSON):
        extract_json("nessun oggetto")
    with pytest.raises(NotJSON):
        extract_json("[1, 2]")
