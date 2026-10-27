"""Il flusso di un turno: (audio -> STT) -> LLM -> (TTS) -> memoria."""
from __future__ import annotations

import base64
import logging
import time

from . import memory, modes
from .providers import llm, stt, tts
from .schemas import TurnResponse

log = logging.getLogger("tutor")


class EmptyInput(ValueError):
    pass


async def run_turn(*, session_id: str, mode: str, level: str, spoken_lang: str,
                   text: str | None = None, audio: bytes | None = None,
                   audio_suffix: str = ".webm", speak: bool = True) -> TurnResponse:
    timings: dict[str, float] = {}

    if text and text.strip():
        transcript = text.strip()
    elif audio:
        t0 = time.perf_counter()
        transcript = await stt.transcribe(audio, spoken_lang, audio_suffix)
        timings["stt"] = round(time.perf_counter() - t0, 2)
    else:
        raise EmptyInput("serve audio o testo")
    if not transcript:
        raise EmptyInput("non ho sentito nulla: riprova")

    system = modes.app_system_prompt(mode, level, spoken_lang)
    hist = memory.history(session_id, mode) if mode in ("conversation", "scenario") else []
    t0 = time.perf_counter()
    kw = {"max_tokens": 900} if mode == "scenario" else {}  # la preparazione elenca più frasi
    tutor, usage = await llm.tutor_reply(system, hist, transcript, **kw)
    timings["llm"] = round(time.perf_counter() - t0, 2)
    # Il modello a volte mette is_correct=false senza alcuna correzione (osservato nel benchmark):
    # per l'allievo conta solo ciò che viene mostrato, quindi "corretto" = nessuna correzione.
    tutor.is_correct = not tutor.corrections
    if usage.get("completion_tokens") and timings["llm"] > 0:
        timings["llm_tok_s"] = round(usage["completion_tokens"] / timings["llm"], 1)

    audio_b64 = audio_mime = None
    if speak and tts.enabled() and tutor.reply:
        t0 = time.perf_counter()
        # In conversazione la domanda di follow-up fa parte del dialogo: va pronunciata, non solo scritta.
        spoken = tutor.reply
        if mode in ("conversation", "scenario") and tutor.follow_up.strip():
            spoken = f"{tutor.reply.strip()} {tutor.follow_up.strip()}"
        try:
            res = await tts.speak(spoken, modes.reply_language(mode, spoken_lang))
            if res:
                audio_b64, audio_mime = base64.b64encode(res[0]).decode(), res[1]
        except Exception as e:  # noqa: BLE001 - il TTS non deve far fallire il turno
            log.warning("TTS fallito: %s", e)
        timings["tts"] = round(time.perf_counter() - t0, 2)

    memory.save_turn(session_id, mode, transcript, tutor)
    return TurnResponse(session_id=session_id, mode=mode, transcript=transcript, tutor=tutor,
                        audio_b64=audio_b64, audio_mime=audio_mime, timings=timings)
