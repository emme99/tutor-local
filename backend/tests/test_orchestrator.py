import asyncio

import pytest

from app import orchestrator
from app.schemas import Correction, TutorOutput


def make_tutor(**overrides):
    data = {
        "is_correct": False,
        "corrected_sentence": "I agree with you.",
        "corrections": [Correction(original="I am agree", corrected="I agree",
                                   explanation_it="Si dice «I agree».", type="grammar")],
        "reply": "I agree with you.",
        "follow_up": "What do you think?",
    }
    data.update(overrides)
    return TutorOutput(**data)


@pytest.fixture
def fake_memory(monkeypatch):
    monkeypatch.setattr(orchestrator.memory, "review_context", lambda: {
        "mistakes": [{"original": "I am agree", "corrected": "I agree"}],
        "vocab": [{"term": "agree", "translation_it": "essere d'accordo"}],
    })
    monkeypatch.setattr(orchestrator.memory, "history", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator.memory, "save_turn", lambda *args, **kwargs: None)


def test_text_turn_adds_review_context_and_normalizes_is_correct(fake_memory, monkeypatch):
    captured = {}

    async def fake_reply(system, history, text, **kwargs):
        captured.update(system=system, history=history, text=text, kwargs=kwargs)
        return make_tutor(), {"completion_tokens": 12}

    monkeypatch.setattr(orchestrator.llm, "tutor_reply", fake_reply)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: False)

    result = asyncio.run(orchestrator.run_turn(
        session_id="s", mode="conversation", level="B1", spoken_lang="en", text=" I am agree "))

    assert result.transcript == "I am agree"
    assert result.tutor.is_correct is False
    assert "REVIEW CONTEXT" in captured["system"]
    assert captured["text"] == "I am agree"
    assert result.timings["llm"] >= 0


def test_is_correct_is_normalized_when_no_corrections_are_shown(fake_memory, monkeypatch):
    async def fake_reply(system, history, text, **kwargs):
        return make_tutor(corrections=[], is_correct=False), {}

    monkeypatch.setattr(orchestrator.llm, "tutor_reply", fake_reply)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: False)

    result = asyncio.run(orchestrator.run_turn(
        session_id="s", mode="conversation", level="B1", spoken_lang="en", text="hello"))
    assert result.tutor.is_correct is True


def test_tts_failure_does_not_fail_turn(fake_memory, monkeypatch):
    async def fake_reply(system, history, text, **kwargs):
        return make_tutor(), {}

    async def broken_tts(*args, **kwargs):
        raise RuntimeError("TTS spento")

    monkeypatch.setattr(orchestrator.llm, "tutor_reply", fake_reply)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: True)
    monkeypatch.setattr(orchestrator.tts, "speak", broken_tts)

    result = asyncio.run(orchestrator.run_turn(
        session_id="s", mode="conversation", level="B1", spoken_lang="en", text="hello"))
    assert result.audio_b64 is None
    assert "tts" in result.timings


def test_explanation_segments_are_created(fake_memory, monkeypatch):
    calls = []

    async def fake_reply(system, history, text, **kwargs):
        return make_tutor(corrections=[Correction(
            original="I am agree", corrected="I agree",
            explanation_it="Si dice «I agree» oppure «I totally agree».",
            type="grammar")]), {}

    async def fake_tts(text, lang, **kwargs):
        calls.append((text, lang))
        return b"audio", "audio/mpeg"

    monkeypatch.setattr(orchestrator.llm, "tutor_reply", fake_reply)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: True)
    monkeypatch.setattr(orchestrator.tts, "speak", fake_tts)

    result = asyncio.run(orchestrator.run_turn(
        session_id="s", mode="conversation", level="B1", spoken_lang="en",
        text="I am agree", speak_explanations=True))
    assert result.audio_b64
    assert len(result.explanations_audio_segments) == 4
    assert calls[0] == ("I agree with you. What do you think?", "en")
    assert calls[1][1] == "it"
    assert calls[2] == ("I agree", "en")


def test_empty_input(fake_memory):
    with pytest.raises(orchestrator.EmptyInput):
        asyncio.run(orchestrator.run_turn(
            session_id="s", mode="conversation", level="B1", spoken_lang="en"))


def test_audio_turn_uses_stt(fake_memory, monkeypatch):
    async def fake_stt(audio, language, suffix):
        assert audio == b"audio"
        assert language == "en"
        assert suffix == ".webm"
        return "hello"

    async def fake_reply(system, history, text, **kwargs):
        return make_tutor(corrections=[], is_correct=True), {}

    monkeypatch.setattr(orchestrator.stt, "transcribe", fake_stt)
    monkeypatch.setattr(orchestrator.llm, "tutor_reply", fake_reply)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: False)

    result = asyncio.run(orchestrator.run_turn(
        session_id="s", mode="conversation", level="B1", spoken_lang="en", audio=b"audio"))
    assert result.transcript == "hello"
    assert "stt" in result.timings


def test_explanation_speech_parts_mixed_languages():
    parts = orchestrator._explanation_speech_parts("Si dice «I agree» per esempio.")
    assert parts == [("Si dice", "it"), ("I agree", "en"), ("per esempio.", "it")]


def test_contextual_help_uses_tagged_segments_for_tts(monkeypatch):
    calls = []

    async def fake_chat(messages, **kwargs):
        return ('{"segments": ['
                '{"lang": "it", "text": "La frase naturale è: "},'
                '{"lang": "en", "text": "I have some free time."},'
                '{"lang": "it", "text": "\\nUsa il present simple."}]}', {})

    async def fake_tts(text, lang, **kwargs):
        calls.append((text, lang))
        return b"audio", "audio/mpeg"

    monkeypatch.setattr(orchestrator.llm, "chat", fake_chat)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: True)
    monkeypatch.setattr(orchestrator.tts, "speak", fake_tts)

    result = asyncio.run(orchestrator.contextual_help(session_id="s", text="come si dice?"))

    assert result.answer == "La frase naturale è: I have some free time.\nUsa il present simple."
    assert calls == [("La frase naturale è:", "it"), ("I have some free time.", "en"),
                     ("Usa il present simple.", "it")]
    assert result.audio_b64 == "YXVkaW8="
    assert len(result.audio_segments) == 2


def test_contextual_help_fallback_marks_unquoted_english_lines(monkeypatch):
    plain = (
        "La frase naturale in inglese è: I have some free time and I would like to improve my English.\n\n"
        "Ecco una breve spiegazione:\n\n"
        "I have some free time (Ho del tempo libero)\n"
        "I would like (Vorrei)\n"
        "To improve (Migliorare)\n\n"
        "In inglese, per esprimere un desiderio in modo gentile, si usa la struttura would like seguita dal verbo "
        "all'infinito.\n\n"
        "Esempi:\n"
        "I would like a coffee (Vorrei un caffè)\n"
        "I would like to travel (Vorrei viaggiare)\n\n"
        "Ricorda che would like è molto più cortese rispetto a I want (Io voglio)."
    )
    calls = []

    async def fake_chat(messages, **kwargs):
        return plain, {}

    async def fake_tts(text, lang, **kwargs):
        calls.append((text, lang))
        return b"audio", "audio/mpeg"

    monkeypatch.setattr(orchestrator.llm, "chat", fake_chat)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: True)
    monkeypatch.setattr(orchestrator.tts, "speak", fake_tts)

    result = asyncio.run(orchestrator.contextual_help(session_id="s", text="come si dice?"))

    assert result.answer == plain
    assert any(lang == "en" and "I have some free time and I would like to improve my English." in text
               for text, lang in calls)
    assert any(lang == "en" and text.startswith("I would like a coffee") for text, lang in calls)
    assert any(lang == "it" and "Vorrei un caffè" in text for text, lang in calls)


def test_contextual_help_retries_invalid_json(monkeypatch):
    responses = iter([
        '{"segments": [broken',
        '{"segments": [{"lang": "it", "text": "Ciao."}]}',
    ])
    calls = []

    async def fake_chat(messages, **kwargs):
        calls.append(messages)
        return next(responses), {}

    monkeypatch.setattr(orchestrator.llm, "chat", fake_chat)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: False)

    result = asyncio.run(orchestrator.contextual_help(session_id="s", text="ciao"))

    assert result.answer == "Ciao."
    assert len(calls) == 2
    assert result.audio_b64 is None
    assert result.audio_segments == []
