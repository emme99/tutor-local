"""Il flusso di un turno: (audio -> STT) -> LLM -> (TTS) -> memoria."""
from __future__ import annotations

import base64
import logging
import re
import time

from . import memory, modes
from .providers import llm, stt, tts
from .schemas import AudioClip, HelpResponse, TurnResponse

log = logging.getLogger("tutor")
_QUOTED_ENGLISH = re.compile(r'“([^”]+)”|«([^»]+)»|„([^“]+)“|"([^"]+)"|‘([^’]+)’|(?<!\w)\'([^\'\n]+)\'(?!\w)')


class EmptyInput(ValueError):
    pass


def _explanation_speech_parts(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in _QUOTED_ENGLISH.finditer(text):
        italian = text[cursor:match.start()].strip()
        if italian.strip(" ,;:-"):
            parts.append((italian, "it"))
        english = next(part for part in match.groups() if part is not None).strip()
        suffix = re.match(r"\s*([,.;:!?])", text[match.end():])
        if suffix:
            english += suffix.group(1)
        if english:
            parts.append((english, "en"))
        cursor = match.end() + suffix.end() if suffix else match.end()
    italian = text[cursor:].strip()
    if italian.strip(" ,;:-"):
        parts.append((italian, "it"))
    return parts


async def run_turn(*, session_id: str, mode: str, level: str, spoken_lang: str,
                   text: str | None = None, audio: bytes | None = None,
                   audio_suffix: str = ".webm", speak: bool = True,
                   speak_explanations: bool = False) -> TurnResponse:
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
    explanations_audio_segments: list[AudioClip] = []
    spoken_parts: list[tuple[str, str]] = []
    if tutor.reply:
        spoken = tutor.reply
        if mode in ("conversation", "scenario") and tutor.follow_up.strip():
            spoken = f"{tutor.reply.strip()} {tutor.follow_up.strip()}"
        spoken_parts.append((spoken, modes.reply_language(mode, spoken_lang)))
    if speak_explanations and mode != "translate":
        explanations = " ".join(c.explanation_it.strip() for c in tutor.corrections if c.explanation_it.strip())
        if explanations:
            spoken_parts.extend(_explanation_speech_parts(explanations))

    if speak and tts.enabled() and spoken_parts:
        t0 = time.perf_counter()
        for index, (spoken, language) in enumerate(spoken_parts):
            try:
                res = await tts.speak(spoken, language)
                if res:
                    encoded = base64.b64encode(res[0]).decode()
                    if index == 0:
                        audio_b64, audio_mime = encoded, res[1]
                    else:
                        explanations_audio_segments.append(AudioClip(audio_b64=encoded, audio_mime=res[1]))
            except Exception as e:  # noqa: BLE001 - il TTS non deve far fallire il turno
                log.warning("TTS fallito (%s): %s", language, e)
        timings["tts"] = round(time.perf_counter() - t0, 2)

    memory.save_turn(session_id, mode, transcript, tutor)
    return TurnResponse(session_id=session_id, mode=mode, transcript=transcript, tutor=tutor,
                        audio_b64=audio_b64, audio_mime=audio_mime,
                        explanations_audio_segments=explanations_audio_segments, timings=timings)


async def contextual_help(*, session_id: str, text: str | None = None,
                          audio: bytes | None = None, audio_suffix: str = ".webm",
                          speak: bool = True) -> HelpResponse:
    timings: dict[str, float] = {}
    if text and text.strip():
        question = text.strip()
    elif audio:
        t0 = time.perf_counter()
        question = await stt.transcribe(audio, "it", audio_suffix)
        timings["stt"] = round(time.perf_counter() - t0, 2)
    else:
        raise EmptyInput("serve una domanda in italiano")
    if not question:
        raise EmptyInput("non ho sentito la domanda: riprova")

    system = (
        "Sei un tutor paziente di inglese per un adulto italiano. Questa è una richiesta di aiuto fuori dal turno di pratica. "
        "Rispondi in italiano in modo chiaro e conciso, di solito entro 120 parole. Usa solo testo semplice: niente Markdown, "
        "asterischi, titoli, elenchi Markdown o formule LaTeX; per elencare forme grammaticali usa una riga semplice per forma. "
        "Spiega grammatica e lessico con esempi brevi in inglese seguiti dalla traduzione italiana. Se l'utente chiede come dire "
        "una frase, fornisci la frase inglese naturale e spiegala in italiano. Usa la conversazione precedente solo come contesto, "
        "non continuare il dialogo e non correggere questa domanda come esercizio. Non inventare informazioni personali "
        "dell'utente e non terminare con una nuova domanda."
    )
    messages = [{"role": "system", "content": system},
                *memory.history(session_id, "conversation"),
                {"role": "user", "content": question}]
    t0 = time.perf_counter()
    answer, _ = await llm.chat(messages, json_mode=False, temperature=0.3, max_tokens=350)
    answer = answer.strip()
    timings["llm"] = round(time.perf_counter() - t0, 2)

    audio_b64 = audio_mime = None
    if speak and tts.enabled() and answer:
        t0 = time.perf_counter()
        try:
            res = await tts.speak(answer, "it")
            if res:
                audio_b64, audio_mime = base64.b64encode(res[0]).decode(), res[1]
        except Exception as e:  # noqa: BLE001 - l'aiuto testuale resta disponibile se il TTS fallisce
            log.warning("TTS aiuto fallito: %s", e)
        timings["tts"] = round(time.perf_counter() - t0, 2)

    return HelpResponse(question=question, answer=answer, audio_b64=audio_b64,
                        audio_mime=audio_mime, timings=timings)
