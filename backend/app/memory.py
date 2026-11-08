"""Memoria dell'allievo in SQLite: turni, errori ricorrenti, vocabolario, ripasso."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from . import review as review_logic
from .config import settings
from .schemas import TutorOutput

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns(
  id INTEGER PRIMARY KEY, ts REAL, session TEXT, mode TEXT, transcript TEXT, tutor_json TEXT);
CREATE TABLE IF NOT EXISTS mistakes(
  id INTEGER PRIMARY KEY, ts REAL, session TEXT, original TEXT, corrected TEXT, type TEXT, explanation_it TEXT);
CREATE TABLE IF NOT EXISTS vocab(
  term TEXT PRIMARY KEY, translation_it TEXT, example TEXT, first_seen REAL, seen INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS review_items(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('mistake','vocab')),
  source_key TEXT NOT NULL,
  prompt TEXT NOT NULL,
  answer TEXT NOT NULL,
  hint TEXT NOT NULL DEFAULT '',
  due REAL NOT NULL,
  interval_days REAL NOT NULL DEFAULT 0,
  ease REAL NOT NULL DEFAULT 2.5,
  repetitions INTEGER NOT NULL DEFAULT 0,
  lapses INTEGER NOT NULL DEFAULT 0,
  last_result INTEGER,
  created REAL NOT NULL,
  last_reviewed REAL,
  UNIQUE(kind, source_key)
);
CREATE INDEX IF NOT EXISTS idx_turns_session_mode ON turns(session, mode, id);
CREATE INDEX IF NOT EXISTS idx_review_due ON review_items(due);
"""

# La versione 1 aggiunge il ripasso e importa gli errori/vocaboli già presenti.
MIGRATIONS = {
    1: """
        INSERT OR IGNORE INTO review_items(kind, source_key, prompt, answer, hint, due, created)
        SELECT 'mistake',
               lower(trim(original)) || char(31) || lower(trim(corrected)),
               original, corrected, explanation_it,
               CAST(strftime('%s','now') AS REAL), ts
        FROM mistakes
        WHERE trim(original) <> ''
          AND id IN (SELECT MIN(id) FROM mistakes
                     GROUP BY lower(trim(original)), lower(trim(corrected)));

        INSERT OR IGNORE INTO review_items(kind, source_key, prompt, answer, hint, due, created)
        SELECT 'vocab', lower(trim(term)), term, translation_it, example,
               CAST(strftime('%s','now') AS REAL), first_seen
        FROM vocab
        WHERE trim(term) <> '';
        """,
}


def _migrate(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    for target, script in MIGRATIONS.items():
        if version < target:
            connection.executescript(script)
            connection.execute(f"PRAGMA user_version = {target}")
            connection.commit()


def _conn() -> sqlite3.Connection:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    _migrate(c)
    return c


def _mistake_key(original: str, corrected: str) -> str:
    return f"{original.strip().lower()}\x1f{corrected.strip().lower()}"


def _upsert_review(c: sqlite3.Connection, kind: str, key: str, prompt: str, answer: str,
                   hint: str, now: float) -> None:
    c.execute(
        "INSERT INTO review_items(kind,source_key,prompt,answer,hint,due,created) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(kind,source_key) DO UPDATE SET prompt=excluded.prompt, answer=excluded.answer, "
        "hint=excluded.hint, due=MIN(review_items.due, excluded.due)",
        (kind, key, prompt, answer, hint, now, now))


def history(session: str, mode: str = "conversation") -> list[dict]:
    """Ultimi turni di conversazione come messaggi chat (l'assistente è il suo JSON, per mantenere il formato)."""
    with closing(_conn()) as c, c:
        rows = c.execute(
            "SELECT transcript, tutor_json FROM turns WHERE session=? AND mode=? "
            "ORDER BY id DESC LIMIT ?", (session, mode, settings.history_turns)).fetchall()
    msgs: list[dict] = []
    for r in reversed(rows):
        msgs += [{"role": "user", "content": r["transcript"]},
                 {"role": "assistant", "content": r["tutor_json"]}]
    return msgs


def save_turn(session: str, mode: str, transcript: str, tutor: TutorOutput) -> None:
    now = time.time()
    with closing(_conn()) as c, c:
        c.execute("INSERT INTO turns(ts,session,mode,transcript,tutor_json) VALUES(?,?,?,?,?)",
                  (now, session, mode, transcript, tutor.model_dump_json()))
        for m in tutor.corrections:
            c.execute("INSERT INTO mistakes(ts,session,original,corrected,type,explanation_it) VALUES(?,?,?,?,?,?)",
                      (now, session, m.original, m.corrected, m.type, m.explanation_it))
            if m.original.strip() and m.corrected.strip():
                _upsert_review(c, "mistake", _mistake_key(m.original, m.corrected),
                               m.original, m.corrected, m.explanation_it, now)
        for v in tutor.new_vocab:
            term = v.term.strip().lower()
            if term:
                c.execute("INSERT INTO vocab(term,translation_it,example,first_seen) VALUES(?,?,?,?) "
                          "ON CONFLICT(term) DO UPDATE SET seen=seen+1", (term, v.translation_it, v.example, now))
                _upsert_review(c, "vocab", term, v.term.strip(), v.translation_it, v.example, now)


def list_vocab(limit: int = 200) -> list[dict]:
    with closing(_conn()) as c, c:
        return [dict(r) for r in c.execute("SELECT * FROM vocab ORDER BY first_seen DESC LIMIT ?", (limit,))]


def list_mistakes(limit: int = 200) -> list[dict]:
    with closing(_conn()) as c, c:
        return [dict(r) for r in c.execute("SELECT * FROM mistakes ORDER BY id DESC LIMIT ?", (limit,))]


def due_reviews(limit: int = 10, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    with closing(_conn()) as c, c:
        rows = c.execute(
            "SELECT * FROM review_items WHERE due<=? ORDER BY due, id LIMIT ?", (now, limit)).fetchall()
        due_count = c.execute("SELECT COUNT(*) FROM review_items WHERE due<=?", (now,)).fetchone()[0]
        total = c.execute("SELECT COUNT(*) FROM review_items").fetchone()[0]
    return {"items": [dict(r) for r in rows], "due_count": due_count, "total": total}


def review_stats(now: float | None = None) -> dict:
    now = time.time() if now is None else now
    with closing(_conn()) as c, c:
        due_count = c.execute("SELECT COUNT(*) FROM review_items WHERE due<=?", (now,)).fetchone()[0]
        total = c.execute("SELECT COUNT(*) FROM review_items").fetchone()[0]
    return {"due_count": due_count, "total": total}


def grade_review(item_id: int, result: int, now: float | None = None) -> dict | None:
    now = time.time() if now is None else now
    with closing(_conn()) as c, c:
        row = c.execute("SELECT * FROM review_items WHERE id=?", (item_id,)).fetchone()
        if not row:
            return None
        interval, ease, repetitions, lapses = review_logic.schedule(
            result, row["interval_days"], row["ease"], row["repetitions"], row["lapses"])
        due = now + interval * 86400
        c.execute(
            "UPDATE review_items SET due=?, interval_days=?, ease=?, repetitions=?, lapses=?, "
            "last_result=?, last_reviewed=? WHERE id=?",
            (due, interval, ease, repetitions, lapses, result, now, item_id))
        return dict(c.execute("SELECT * FROM review_items WHERE id=?", (item_id,)).fetchone())


def review_context(now: float | None = None, limit: int = 3) -> dict:
    """Materiale scaduto da riusare nel prompt dell'app (non nel benchmark)."""
    now = time.time() if now is None else now
    with closing(_conn()) as c, c:
        mistakes = [dict(r) for r in c.execute(
            "SELECT r.prompt AS original, r.answer AS corrected, r.hint AS explanation_it, "
            "       COUNT(m.id) AS occurrences "
            "FROM review_items r "
            "LEFT JOIN mistakes m ON lower(trim(m.original))=lower(trim(r.prompt)) "
            "                    AND lower(trim(m.corrected))=lower(trim(r.answer)) "
            "WHERE r.kind='mistake' AND r.due<=? "
            "GROUP BY r.id ORDER BY occurrences DESC, r.due, r.id LIMIT ?", (now, limit))]
        vocab = [dict(r) for r in c.execute(
            "SELECT prompt AS term, answer AS translation_it FROM review_items "
            "WHERE kind='vocab' AND due<=? ORDER BY due, id LIMIT ?", (now, limit))]
    return {"mistakes": mistakes, "vocab": vocab}


def session_summary(session: str) -> dict:
    with closing(_conn()) as c, c:
        rows = c.execute("SELECT ts, mode, tutor_json FROM turns WHERE session=? ORDER BY id",
                         (session,)).fetchall()
    modes: dict[str, int] = {}
    corrections: list[dict] = []
    vocab: list[dict] = []
    seen_corrections: set[tuple[str, str]] = set()
    seen_vocab: set[str] = set()
    for row in rows:
        modes[row["mode"]] = modes.get(row["mode"], 0) + 1
        try:
            data = json.loads(row["tutor_json"] or "{}")
        except (TypeError, ValueError):
            continue
        for correction in data.get("corrections") or []:
            key = (str(correction.get("original", "")).strip().lower(),
                   str(correction.get("corrected", "")).strip().lower())
            if key not in seen_corrections:
                seen_corrections.add(key)
                corrections.append(correction)
        for item in data.get("new_vocab") or []:
            key = str(item.get("term", "")).strip().lower()
            if key and key not in seen_vocab:
                seen_vocab.add(key)
                vocab.append(item)
    return {
        "session": session,
        "turns": len(rows),
        "modes": modes,
        "corrections": corrections,
        "vocab": vocab,
        "started": rows[0]["ts"] if rows else None,
        "ended": rows[-1]["ts"] if rows else None,
    }
