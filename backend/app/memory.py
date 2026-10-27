"""Memoria dell'allievo in SQLite: turni, errori ricorrenti, vocabolario."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .config import settings
from .schemas import TutorOutput

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns(
  id INTEGER PRIMARY KEY, ts REAL, session TEXT, mode TEXT, transcript TEXT, tutor_json TEXT);
CREATE TABLE IF NOT EXISTS mistakes(
  id INTEGER PRIMARY KEY, ts REAL, session TEXT, original TEXT, corrected TEXT, type TEXT, explanation_it TEXT);
CREATE TABLE IF NOT EXISTS vocab(
  term TEXT PRIMARY KEY, translation_it TEXT, example TEXT, first_seen REAL, seen INTEGER DEFAULT 1);
"""


def _conn() -> sqlite3.Connection:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def history(session: str, mode: str = "conversation") -> list[dict]:
    """Ultimi turni di conversazione come messaggi chat (l'assistente è il suo JSON, per mantenere il formato)."""
    with _conn() as c:
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
    with _conn() as c:
        c.execute("INSERT INTO turns(ts,session,mode,transcript,tutor_json) VALUES(?,?,?,?,?)",
                  (now, session, mode, transcript, tutor.model_dump_json()))
        for m in tutor.corrections:
            c.execute("INSERT INTO mistakes(ts,session,original,corrected,type,explanation_it) VALUES(?,?,?,?,?,?)",
                      (now, session, m.original, m.corrected, m.type, m.explanation_it))
        for v in tutor.new_vocab:
            term = v.term.strip().lower()
            if term:
                c.execute("INSERT INTO vocab(term,translation_it,example,first_seen) VALUES(?,?,?,?) "
                          "ON CONFLICT(term) DO UPDATE SET seen=seen+1", (term, v.translation_it, v.example, now))


def list_vocab(limit: int = 200) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM vocab ORDER BY first_seen DESC LIMIT ?", (limit,))]


def list_mistakes(limit: int = 200) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM mistakes ORDER BY id DESC LIMIT ?", (limit,))]
