from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import memory, orchestrator, phonetics
from .config import settings
from .errors import TutorError
from .providers import llm, tts
from .schemas import (
    HelpResponse,
    PronunciationCheck,
    ReviewGradeIn,
    ReviewGradeOut,
    ReviewQueue,
    ReviewStats,
    SessionSummary,
    TurnResponse,
)

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="tutor-local")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                allow_methods=["*"], allow_headers=["*"])
TTS_SPEEDS = (0.3, 0.7, 1.0)


@app.exception_handler(TutorError)
async def tutor_error_handler(_request, exc: TutorError):
    if exc.status_code >= 500:
        logging.getLogger("tutor").warning("%s", exc)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.exception_handler(orchestrator.EmptyInput)
async def empty_input_handler(_request, exc: orchestrator.EmptyInput):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPError)
async def httpx_error_handler(_request, exc: httpx.HTTPError):
    # Rete di sicurezza: i provider traducono già gli errori in TutorError.
    logging.getLogger("tutor").warning("errore HTTP non gestito: %s", exc)
    return JSONResponse(status_code=502, content={"detail": f"servizio locale non disponibile: {exc}"})


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_request, exc: RuntimeError):
    # Problemi locali (es. ffmpeg mancante): messaggio leggibile senza esporre uno stack trace.
    logging.getLogger("tutor").exception("errore locale: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
async def health():
    return {"llm": {"base_url": settings.llm_base_url, "model": settings.llm_model},
            "stt_model": settings.stt_model, "tts_enabled": tts.enabled()}


@app.post("/api/turn", response_model=TurnResponse)
async def turn(session_id: str = Form(...), mode: str = Form("conversation"), level: str = Form("B1"),
               spoken_lang: str = Form("en"), text: str | None = Form(None),
               speak: bool = Form(True), speak_explanations: bool = Form(False),
               tts_speed: float = Form(1.0), audio: UploadFile | None = File(None)):
    if mode not in ("conversation", "translate", "scenario") or spoken_lang not in ("en", "it"):
        raise HTTPException(400, "mode o spoken_lang non validi")
    if tts_speed not in TTS_SPEEDS:
        raise HTTPException(400, "tts_speed deve essere 0.3, 0.7, 1.0")
    data = await audio.read() if audio else None
    suffix = Path(audio.filename or "turn.webm").suffix or ".webm" if audio else ".webm"
    return await orchestrator.run_turn(session_id=session_id, mode=mode, level=level,
                                       spoken_lang=spoken_lang, text=text, audio=data,
                                       audio_suffix=suffix, speak=speak,
                                       speak_explanations=speak_explanations, tts_speed=tts_speed)


@app.post("/api/help", response_model=HelpResponse)
async def contextual_help(session_id: str = Form(...), text: str | None = Form(None),
                          tts_speed: float = Form(1.0), audio: UploadFile | None = File(None)):
    if not (text and text.strip()) and not audio:
        raise HTTPException(400, "serve una domanda in italiano")
    if tts_speed not in TTS_SPEEDS:
        raise HTTPException(400, "tts_speed deve essere 0.3, 0.7, 1.0")
    data = await audio.read() if audio else None
    suffix = Path(audio.filename or "help.webm").suffix or ".webm" if audio else ".webm"
    return await orchestrator.contextual_help(session_id=session_id, text=text,
                                              audio=data, audio_suffix=suffix, tts_speed=tts_speed)


@app.get("/api/vocab")
async def vocab():
    return memory.list_vocab()


@app.get("/api/mistakes")
async def mistakes():
    return memory.list_mistakes()


@app.get("/api/review/due", response_model=ReviewQueue)
async def review_due(limit: int = 10):
    if not 1 <= limit <= 50:
        raise HTTPException(400, "limit deve essere tra 1 e 50")
    return memory.due_reviews(limit=limit)


@app.get("/api/review/stats", response_model=ReviewStats)
async def review_stats():
    return memory.review_stats()


@app.post("/api/review/grade", response_model=ReviewGradeOut)
async def review_grade(body: ReviewGradeIn):
    item = memory.grade_review(body.id, body.result)
    if not item:
        raise HTTPException(404, "elemento di ripasso non trovato")
    return {"item": item, **memory.review_stats()}


@app.get("/api/session/{session_id}/summary", response_model=SessionSummary)
async def session_summary(session_id: str):
    return memory.session_summary(session_id)


class TranslateIn(BaseModel):
    text: str
    target: str = "it"


@app.post("/api/translate")
async def translate(body: TranslateIn):
    """Traduzione al volo di una risposta del tutor (non entra nella cronologia né nel vocabolario)."""
    name = {"it": "Italian", "en": "English"}.get(body.target)
    if not name or not body.text.strip():
        raise HTTPException(400, "testo o lingua non validi")
    out, _ = await llm.chat(
        [{"role": "system", "content": f"Translate the user's text into {name}. Output only the translation."},
         {"role": "user", "content": body.text}],
        json_mode=False, temperature=0.2, max_tokens=300)
    return {"translation": out.strip()}

class SpeakIn(BaseModel):
    text: str
    lang: str = "en"
    speed: float = 1.0


@app.post("/api/speak")
async def speak(body: SpeakIn):
    """Pronuncia una singola frase (es. una frase suggerita in uno scenario)."""
    if body.lang not in ("en", "it") or not body.text.strip() or body.speed not in TTS_SPEEDS:
        raise HTTPException(400, "testo, lingua o velocità non validi")
    if not tts.enabled():
        raise HTTPException(503, "TTS non configurato (TTS_BASE_URL)")
    res = await tts.speak(body.text, body.lang, speed=body.speed)
    if not res:
        raise HTTPException(502, "il TTS non ha prodotto audio")
    return {"audio_b64": base64.b64encode(res[0]).decode(), "audio_mime": res[1]}


@app.post("/api/pronunciation-check", response_model=PronunciationCheck)
async def pronunciation_check(target: str = Form(...), audio: UploadFile = File(...)):
    """Valuta la pronuncia di una ripetizione rispetto alla frase inglese attesa."""
    if not target.strip() or len(target) > 500:
        raise HTTPException(400, "frase attesa non valida")
    data = await audio.read()
    suffix = Path(audio.filename or "turn.webm").suffix or ".webm"
    return await phonetics.evaluate_pronunciation(target, data, "en", suffix)


# Frontend compilato (npm run build): se presente viene servito qui, quindi basta un solo processo e Node non serve a runtime.
# Va montato per ultimo, dopo tutte le rotte /api.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
