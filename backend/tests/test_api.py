import httpx

from app import memory, orchestrator
from app.errors import LLMUnavailable, STTUnavailable
from app.schemas import Correction, TutorOutput, VocabItem


def tutor():
    return TutorOutput(
        is_correct=False, corrected_sentence="I agree.",
        corrections=[Correction(original="I am agree", corrected="I agree",
                                explanation_it="Si dice I agree.", type="grammar")],
        reply="Good.", new_vocab=[VocabItem(term="agree", translation_it="essere d'accordo")],
    )


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "llm" in response.json()


def test_invalid_mode(client):
    response = client.post("/api/turn", data={"session_id": "s", "mode": "boh", "text": "hi"})
    assert response.status_code == 400


def test_empty_input_is_400(client, monkeypatch):
    async def empty(*args, **kwargs):
        raise orchestrator.EmptyInput("non ho sentito nulla: riprova")

    monkeypatch.setattr(orchestrator, "run_turn", empty)
    response = client.post("/api/turn", data={"session_id": "s", "mode": "conversation", "text": " "})
    assert response.status_code == 400
    assert "non ho sentito" in response.json()["detail"]


def test_llm_error_is_reported_with_service_name(client, monkeypatch):
    async def broken(*args, **kwargs):
        raise LLMUnavailable("non raggiungibile su http://localhost:11434/v1")

    monkeypatch.setattr(orchestrator, "run_turn", broken)
    response = client.post("/api/turn", data={"session_id": "s", "mode": "conversation", "text": "hello"})
    assert response.status_code == 502
    assert response.json()["detail"].startswith("LLM:")


def test_stt_error_is_not_mislabeled_as_llm(client, monkeypatch):
    async def broken(*args, **kwargs):
        raise STTUnavailable("server spento")

    monkeypatch.setattr(orchestrator, "run_turn", broken)
    response = client.post("/api/turn", data={"session_id": "s", "mode": "conversation", "text": "hello"})
    assert response.status_code == 502
    assert response.json()["detail"].startswith("STT:")


def test_timeout_fallback_is_502(client, monkeypatch):
    async def broken(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(orchestrator, "run_turn", broken)
    response = client.post("/api/turn", data={"session_id": "s", "mode": "conversation", "text": "hello"})
    assert response.status_code == 502


def test_translate(client, monkeypatch):
    from app import main as main_module

    async def fake_chat(messages, **kwargs):
        return "ciao", {}

    monkeypatch.setattr(main_module.llm, "chat", fake_chat)
    response = client.post("/api/translate", json={"text": "hello", "target": "it"})
    assert response.status_code == 200
    assert response.json() == {"translation": "ciao"}


def test_speak_without_tts_is_503(client):
    response = client.post("/api/speak", json={"text": "hello", "lang": "en"})
    assert response.status_code == 503


def test_pronunciation_check(client, monkeypatch):
    async def fake_evaluate(target, audio, lang="en", suffix=".webm"):
        assert target == "I would like a coffee"
        assert lang == "en"
        return {
            "expected": target,
            "score": 82,
            "matched_phones": 21,
            "total_phones": 26,
            "expected_ipa": "aɪ w ʊ d l aɪ k ə k ɔ f i",
            "predicted_ipa": "aɪ w u d l aɪ k ə k ɔ f i",
            "short_target": False,
            "verdict": None,
            "ops": [{"op": "match", "expected": "aɪ", "heard": "aɪ"}],
            "words": [{"word": "I", "expected_ipa": "aɪ", "heard_ipa": "aɪ", "score": 100,
                       "ops": [{"op": "match", "expected": "aɪ", "heard": "aɪ"}]}],
        }

    monkeypatch.setattr("app.main.phonetics.evaluate_pronunciation", fake_evaluate)
    response = client.post(
        "/api/pronunciation-check",
        data={"target": "I would like a coffee"},
        files={"audio": ("turn.webm", b"fake", "audio/webm")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 82
    assert data["matched_phones"] == 21
    assert data["total_phones"] == 26
    assert data["expected_ipa"].startswith("aɪ")
    assert data["predicted_ipa"].startswith("aɪ")
    assert data["short_target"] is False
    assert data["verdict"] is None
    assert len(data["ops"]) == 1
    assert len(data["words"]) == 1
    assert data["words"][0]["word"] == "I"


def test_pronunciation_check_short_target(client, monkeypatch):
    async def fake_evaluate(target, audio, lang="en", suffix=".webm"):
        assert target == "towel"
        return {
            "expected": "towel",
            "score": 70,
            "matched_phones": 3,
            "total_phones": 4,
            "expected_ipa": "t aʊ ə l",
            "predicted_ipa": "t a b ɔ l",
            "short_target": True,
            "verdict": "da_rivedere",
            "ops": [
                {"op": "match", "expected": "t", "heard": "t"},
                {"op": "sub", "expected": "aʊ", "heard": "b"},
            ],
            "words": [{"word": "towel", "expected_ipa": "t aʊ ə l", "heard_ipa": "t a b ɔ l", "score": 70, "ops": []}],
        }

    monkeypatch.setattr("app.main.phonetics.evaluate_pronunciation", fake_evaluate)
    response = client.post(
        "/api/pronunciation-check",
        data={"target": "towel"},
        files={"audio": ("turn.webm", b"fake", "audio/webm")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["short_target"] is True
    assert data["verdict"] == "da_rivedere"


def test_help_returns_tagged_audio_segments(client, monkeypatch):
    async def fake_chat(messages, **kwargs):
        return ('{"segments": [{"lang": "it", "text": "Ciao. "},'
                '{"lang": "en", "text": "Hello."}]}', {})

    async def fake_tts(text, lang, **kwargs):
        assert lang in ("it", "en")
        return b"audio", "audio/mpeg"

    monkeypatch.setattr(orchestrator.llm, "chat", fake_chat)
    monkeypatch.setattr(orchestrator.tts, "enabled", lambda: True)
    monkeypatch.setattr(orchestrator.tts, "speak", fake_tts)

    response = client.post("/api/help", data={"session_id": "s", "text": "come si dice hello?"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Ciao. Hello."
    assert data["audio_b64"] == "YXVkaW8="
    assert len(data["audio_segments"]) == 1
    assert data["audio_segments"][0]["audio_b64"] == "YXVkaW8="


def test_review_endpoints_and_summary(client, monkeypatch):
    # Evita di chiamare STT/LLM reali: il turno passa direttamente da un tutor finto.
    async def fake_turn(**kwargs):
        from app.schemas import TurnResponse
        memory.save_turn(kwargs["session_id"], kwargs["mode"], kwargs["text"], tutor())
        return TurnResponse(session_id=kwargs["session_id"], mode=kwargs["mode"],
                            transcript=kwargs["text"], tutor=tutor())

    monkeypatch.setattr(orchestrator, "run_turn", fake_turn)
    response = client.post("/api/turn", data={"session_id": "s1", "mode": "conversation", "text": "a"})
    assert response.status_code == 200

    queue = client.get("/api/review/due").json()
    assert queue["due_count"] == 2
    item = queue["items"][0]
    graded = client.post("/api/review/grade", json={"id": item["id"], "result": 2})
    assert graded.status_code == 200
    assert graded.json()["item"]["repetitions"] == 1
    assert client.post("/api/review/grade", json={"id": 999, "result": 2}).status_code == 404

    summary = client.get("/api/session/s1/summary").json()
    assert summary["turns"] == 1
    assert len(summary["corrections"]) == 1
    assert client.get("/api/session/sconosciuta/summary").json()["turns"] == 0
