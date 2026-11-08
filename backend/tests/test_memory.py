import json
import sqlite3
import time

from app import memory
from app.schemas import Correction, TutorOutput, VocabItem


def make_tutor():
    return TutorOutput(
        is_correct=False,
        corrected_sentence="I agree with you.",
        corrections=[Correction(original="I am agree", corrected="I agree",
                                explanation_it="Si dice I agree.", type="grammar")],
        reply="I agree with you.",
        follow_up="What do you think?",
        new_vocab=[VocabItem(term="agree", translation_it="essere d'accordo",
                             example="I agree with you.")],
    )


def test_save_and_scope_history(temp_settings, monkeypatch):
    memory.save_turn("s1", "conversation", "I am agree", make_tutor())
    memory.save_turn("s1", "translate", "ciao", make_tutor())
    memory.save_turn("s2", "conversation", "I am agree", make_tutor())

    history = memory.history("s1", "conversation")
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "I am agree"
    assert json.loads(history[1]["content"])["reply"] == "I agree with you."

    from dataclasses import replace
    monkeypatch.setattr(memory, "settings", replace(temp_settings, history_turns=1))
    assert len(memory.history("s1", "conversation")) == 2


def test_vocab_upsert_and_review_creation(temp_settings):
    memory.save_turn("s1", "conversation", "a", make_tutor())
    memory.save_turn("s1", "conversation", "b", make_tutor())
    vocab = memory.list_vocab()
    assert len(vocab) == 1
    assert vocab[0]["seen"] == 2

    queue = memory.due_reviews(now=time.time() + 1)
    assert queue["due_count"] == 2  # un errore + un vocabolo
    assert {item["kind"] for item in queue["items"]} == {"mistake", "vocab"}

    context = memory.review_context(now=time.time() + 1)
    assert context["mistakes"][0]["original"] == "I am agree"
    assert context["vocab"][0]["term"] == "agree"


def test_grade_moves_item_out_of_queue(temp_settings):
    memory.save_turn("s1", "conversation", "a", make_tutor())
    item = memory.due_reviews(now=time.time() + 1)["items"][0]
    updated = memory.grade_review(item["id"], 2)
    assert updated is not None
    assert updated["repetitions"] == 1
    assert updated["due"] > time.time()
    assert memory.grade_review(999999, 2) is None


def test_summary_deduplicates_corrections_and_vocab(temp_settings):
    memory.save_turn("s1", "conversation", "a", make_tutor())
    memory.save_turn("s1", "conversation", "b", make_tutor())
    summary = memory.session_summary("s1")
    assert summary["turns"] == 2
    assert summary["modes"] == {"conversation": 2}
    assert len(summary["corrections"]) == 1
    assert len(summary["vocab"]) == 1


def test_migration_backfills_existing_data(temp_settings):
    # Simula un database della versione precedente (senza review_items, user_version=0).
    with sqlite3.connect(temp_settings.db_path) as c:
        c.executescript("""
        CREATE TABLE mistakes(
          id INTEGER PRIMARY KEY, ts REAL, session TEXT, original TEXT, corrected TEXT, type TEXT, explanation_it TEXT);
        CREATE TABLE vocab(
          term TEXT PRIMARY KEY, translation_it TEXT, example TEXT, first_seen REAL, seen INTEGER DEFAULT 1);
        """)
        c.execute("INSERT INTO mistakes(ts,session,original,corrected,type,explanation_it) "
                  "VALUES(1,'old','I am agree','I agree','grammar','Si dice I agree.')")
        c.execute("INSERT INTO vocab(term,translation_it,example,first_seen,seen) "
                  "VALUES('agree','essere d''accordo','I agree.',1,1)")
        c.execute("PRAGMA user_version = 0")

    items = memory.due_reviews(now=time.time() + 1)
    assert items["total"] == 2
    assert any(item["prompt"] == "I am agree" for item in items["items"])
    assert any(item["prompt"] == "agree" for item in items["items"])
