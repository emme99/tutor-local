from __future__ import annotations

import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from . import memory, orchestrator
from .config import settings
from .jsonparse import NotJSON
from .providers import llm, tts
from .schemas import TurnResponse

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="tutor-local")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"llm": {"base_url": settings.llm_base_url, "model": settings.llm_model},
            "stt_model": settings.stt_model, "tts_enabled": tts.enabled()}


@app.post("/api/turn", response_model=TurnResponse)
async def turn(session_id: str = Form(...), mode: str = Form("conversation"), level: str = Form("B1"),
               spoken_lang: str = Form("en"), text: str | None = Form(None),
               speak: bool = Form(True), audio: UploadFile | None = File(None)):
    if mode not in ("conversation", "translate", "scenario") or spoken_lang not in ("en", "it"):
        raise HTTPException(400, "mode o spoken_lang non validi")
    data = await audio.read() if audio else None
    suffix = Path(audio.filename or "turn.webm").suffix or ".webm" if audio else ".webm"
    try:
        return await orchestrator.run_turn(session_id=session_id, mode=mode, level=level,
                                           spoken_lang=spoken_lang, text=text, audio=data,
                                           audio_suffix=suffix, speak=speak)
    except orchestrator.EmptyInput as e:
        raise HTTPException(400, str(e)) from e
    except httpx.ConnectError as e:
        raise HTTPException(502, f"LLM non raggiungibile su {settings.llm_base_url}: avvia Ollama/LM Studio") from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"LLM ha risposto {e.response.status_code}: {e.response.text[:200]}") from e
    except (NotJSON, ValidationError) as e:
        raise HTTPException(502, f"Il modello non ha prodotto il JSON atteso: {e}") from e
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/vocab")
async def vocab():
    return memory.list_vocab()


@app.get("/api/mistakes")
async def mistakes():
    return memory.list_mistakes()


class TranslateIn(BaseModel):
    text: str
    target: str = "it"


@app.post("/api/translate")
async def translate(body: TranslateIn):
    """Traduzione al volo di una risposta del tutor (non entra nella cronologia né nel vocabolario)."""
    name = {"it": "Italian", "en": "English"}.get(body.target)
    if not name or not body.text.strip():
        raise HTTPException(400, "testo o lingua non validi")
    try:
        out, _ = await llm.chat(
            [{"role": "system", "content": f"Translate the user's text into {name}. Output only the translation."},
             {"role": "user", "content": body.text}],
            json_mode=False, temperature=0.2, max_tokens=300)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"LLM non disponibile: {e}") from e
    return {"translation": out.strip()}


class SpeakIn(BaseModel):
    text: str
    lang: str = "en"


@app.post("/api/speak")
async def speak(body: SpeakIn):
    """Pronuncia una singola frase (es. una frase suggerita in uno scenario)."""
    if body.lang not in ("en", "it") or not body.text.strip():
        raise HTTPException(400, "testo o lingua non validi")
    if not tts.enabled():
        raise HTTPException(503, "TTS non configurato (TTS_BASE_URL)")
    try:
        res = await tts.speak(body.text, body.lang)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"TTS non disponibile: {e}") from e
    if not res:
        raise HTTPException(502, "il TTS non ha prodotto audio")
    import base64
    return {"audio_b64": base64.b64encode(res[0]).decode(), "audio_mime": res[1]}


# Frontend compilato (npm run build): se presente viene servito qui, quindi basta un solo processo e Node non serve a runtime.
# Va montato per ultimo, dopo tutte le rotte /api.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
