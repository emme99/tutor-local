from app import modes


def test_benchmark_prompt_has_no_persona_and_no_review_block():
    prompt = modes.system_prompt("conversation", "B1", "en")
    assert "Your name is Alex" not in prompt
    assert "REVIEW CONTEXT" not in prompt
    assert "suggested_reply" in prompt


def test_app_prompt_adds_persona_in_conversation_and_scenario():
    for mode in ("conversation", "scenario"):
        assert "Your name is Alex" in modes.app_system_prompt(mode, "B1", "en")
    assert "Your name is Alex" not in modes.app_system_prompt("translate", "B1", "en")


def test_translate_direction():
    assert "speech in English" in modes.system_prompt("translate", "B1", "en")
    assert "speech in Italian" in modes.system_prompt("translate", "B1", "it")
    assert modes.reply_language("translate", "en") == "it"
    assert modes.reply_language("translate", "it") == "en"


def test_review_addendum_is_compact_and_hidden_when_empty():
    assert modes.review_addendum({}) == ""
    block = modes.review_addendum({
        "mistakes": [{"original": "I am agree", "corrected": "I agree"}],
        "vocab": [{"term": "agree", "translation_it": "essere d'accordo"}],
    })
    assert "I am agree" in block
    assert "agree" in block
    assert "never mention" in block
