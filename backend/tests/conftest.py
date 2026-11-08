from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "llm_bench"))


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    """Configurazione isolata: nessun test tocca data/tutor.db né i servizi reali."""
    from app import config, main, memory
    from app.providers import llm, stt, tts

    current = replace(
        config.settings,
        db_path=str(tmp_path / "tutor.db"),
        tts_base_url="",
        stt_backend="openai",
        history_turns=6,
    )
    for module in (config, main, memory, llm, stt, tts):
        monkeypatch.setattr(module, "settings", current)
    return current


@pytest.fixture
def client(temp_settings):
    from app.main import app

    return TestClient(app)
