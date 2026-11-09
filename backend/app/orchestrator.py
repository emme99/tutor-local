"""Il flusso di un turno: (audio -> STT) -> LLM -> (TTS) -> memoria."""
from __future__ import annotations

import base64
import logging
import re
import time

from . import memory, modes
from .jsonparse import NotJSON, extract_json
from .providers import llm, stt, tts
from .schemas import AudioClip, HelpResponse, TurnResponse

log = logging.getLogger("tutor")
_QUOTED_ENGLISH = re.compile(r'“([^”]+)”|«([^»]+)»|„([^“]+)“|"([^"]+)"|‘([^’]+)’|(?<!\w)\'([^\'\n]+)\'(?!\w)')

# Riconoscimento usato solo come rete di sicurezza quando il modello non tagga le lingue.
# La via principale è il JSON con segmenti `{lang, text}`.
_ITALIAN_MARKERS = frozenset({
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "del", "dello", "della", "dei",
    "degli", "delle", "che", "chi", "cui", "è", "sono", "sei", "siamo", "siete", "per", "con",
    "non", "si", "come", "più", "ma", "anche", "questo", "questa", "questi", "queste", "quando",
    "perché", "cosa", "fare", "dire", "usare", "inglese", "italiano", "frase", "frasi", "parola",
    "parole", "verbo", "verbi", "esempio", "esempi", "significa", "significato", "struttura",
    "seguita", "seguito", "modo", "gentile", "desiderio", "tempo", "libero", "vorrei", "ho",
    "hai", "abbiamo", "avete", "hanno", "essere", "avere", "posso", "puoi", "deve", "dobbiamo",
    "dovete", "devono", "molto", "poco", "bene", "male", "qui", "qua", "adesso", "ora", "oggi",
    "domani", "ieri", "sempre", "mai", "già", "ancora", "invece", "quindi", "allora", "oppure",
    "cioè", "infatti", "inoltre", "tuttavia", "però", "senza", "tra", "fra", "sul", "sulla",
    "nel", "nella", "nell", "all", "dall", "dell", "sull", "l", "d", "c",
})
_ENGLISH_MARKERS = frozenset({
    "the", "and", "is", "are", "am", "was", "were", "be", "been", "being", "to", "of", "or",
    "but", "in", "on", "at", "for", "with", "from", "this", "that", "these", "those", "you",
    "your", "yours", "i", "we", "they", "he", "she", "it", "its", "would", "have", "has",
    "had", "do", "does", "did", "can", "could", "will", "should", "may", "might", "must",
    "like", "not", "my", "me", "him", "her", "us", "them", "some", "any", "very", "more",
    "most", "much", "many", "also", "because", "when", "where", "what", "which", "who", "how",
    "there", "here", "now", "today", "tomorrow", "yesterday", "always", "never", "already",
    "still", "instead", "so", "then", "however", "without", "between", "about", "after",
    "before", "during", "through", "please", "thanks", "thank", "coffee", "water", "time",
    "free", "improve", "english", "italian", "phrase", "word", "sentence", "example",
    "structure", "followed", "kind", "want", "wants", "wanted", "going", "get", "got", "make",
    "made", "take", "took", "see", "saw", "look", "looking", "say", "said", "tell", "told",
    "speak", "speaking", "learn", "learning", "book", "room", "hotel", "night", "work", "job",
    "interview", "doctor", "restaurant", "airport", "don", "isn", "aren", "wasn", "weren",
    "couldn", "wouldn", "shouldn", "won", "let",
})
_PAREN = re.compile(r"(\([^)]*\)|\[[^\]]*\])")
_SEPARATOR = re.compile(r"(\s+[-–—=→]\s+|:\s+)")


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


def _merge_speech_parts(parts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Unisce parti adiacenti nella stessa lingua, senza perdere spazi e a capo."""
    merged: list[tuple[str, str]] = []
    for text, language in parts:
        if not text:
            continue
        if merged and merged[-1][1] == language:
            merged[-1] = (merged[-1][0] + text, language)
        else:
            merged.append((text, language))
    return merged


def _looks_english(text: str) -> bool:
    lowered = text.lower()
    words = re.findall(r"[a-z]+", lowered)
    if not words:
        return False
    italian = sum(1 for word in words if word in _ITALIAN_MARKERS)
    english = sum(1 for word in words if word in _ENGLISH_MARKERS)
    if re.search(r"[àèéìòù]", lowered):
        italian += 2
    # Almeno due parole funzionali inglesi e più inglese che italiano: evita di
    # classificare come inglese una frase italiana che contiene un termine inglese.
    return english >= 2 and english > italian


def _split_line_by_language(line: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    for chunk in _PAREN.split(line):
        if not chunk:
            continue
        for piece in _SEPARATOR.split(chunk):
            if not piece:
                continue
            if not piece.strip():
                if parts:
                    text, language = parts[-1]
                    parts[-1] = (text + piece, language)
                continue
            parts.append((piece, "en" if _looks_english(piece) else "it"))
    return _merge_speech_parts(parts)


def _split_italian_text(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    pending = ""
    for line in text.splitlines(keepends=True):
        if not line.strip():
            if parts:
                previous, language = parts[-1]
                parts[-1] = (previous + line, language)
            else:
                pending += line
            continue
        parts.extend(_split_line_by_language(pending + line))
        pending = ""
    if pending:
        if parts:
            previous, language = parts[-1]
            parts[-1] = (previous + pending, language)
        else:
            parts.append((pending, "it"))
    return _merge_speech_parts(parts)


def _help_parts_from_text(text: str) -> list[tuple[str, str]]:
    """Segmenta una risposta libera: virgolette, righe e traduzioni tra parentesi."""
    parts: list[tuple[str, str]] = []
    for chunk, language in _explanation_speech_parts(text):
        if language == "en":
            parts.append((chunk, "en"))
        else:
            parts.extend(_split_italian_text(chunk))
    return _merge_speech_parts(parts)


def _normalize_help_parts(parts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Raffina i segmenti del modello: le parti italiane possono contenere esempi non taggati."""
    normalized: list[tuple[str, str]] = []
    for text, language in parts:
        if not text:
            continue
        if language == "en":
            normalized.append((text, "en"))
        else:
            normalized.extend(_split_italian_text(text))
    return _merge_speech_parts(normalized)


def _join_help_parts(parts: list[tuple[str, str]]) -> str:
    """Ricostruisce il testo da mostrare preservando spazi e a capo dei segmenti."""
    answer = ""
    for text, _ in parts:
        if not text:
            continue
        if answer and not answer[-1].isspace() and not text[0].isspace():
            if text[0] not in ",.;:!?)]}" and answer[-1] not in "([{":
                answer += " "
        answer += text
    return answer.strip()


def _parse_help_segments(raw: str) -> list[tuple[str, str]] | None:
    """Estrae `{"segments": [{"lang": "it|en", "text": "..."}]}` dall'output del modello."""
    try:
        obj = extract_json(raw)
    except NotJSON:
        return None
    segments = obj.get("segments")
    if not isinstance(segments, list):
        return None
    parts: list[tuple[str, str]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = segment.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        language = str(segment.get("lang") or "it").strip().lower()
        english = language.startswith("en") or language in {"english", "inglese"}
        parts.append((text, "en" if english else "it"))
    return _normalize_help_parts(parts) if parts else None


async def _help_answer(messages: list[dict]) -> tuple[str, list[tuple[str, str]], dict]:
    kwargs = {"temperature": 0.3, "max_tokens": 600}
    raw, usage = await llm.chat(messages, **kwargs)
    parts = _parse_help_segments(raw)
    if parts is not None:
        return _join_help_parts(parts), parts, usage
    if raw.lstrip().startswith("{"):
        # Il modello ha tentato il JSON ma non è valido: un solo retry, come per il turno.
        retry = [*messages, {"role": "assistant", "content": raw},
                 {"role": "user", "content": "Rispondi di nuovo SOLO con l'oggetto JSON richiesto, senza altro testo."}]
        raw2, usage2 = await llm.chat(retry, **kwargs)
        usage = {
            **usage,
            "prompt_tokens": (usage.get("prompt_tokens") or 0) + (usage2.get("prompt_tokens") or 0),
            "completion_tokens": (usage.get("completion_tokens") or 0) + (usage2.get("completion_tokens") or 0),
        }
        parts = _parse_help_segments(raw2)
        if parts is not None:
            return _join_help_parts(parts), parts, usage
        raw = raw2
    answer = raw.strip()
    return answer, _help_parts_from_text(answer), usage


async def run_turn(*, session_id: str, mode: str, level: str, spoken_lang: str,
                   text: str | None = None, audio: bytes | None = None,
                   audio_suffix: str = ".webm", speak: bool = True,
                   speak_explanations: bool = False, tts_speed: float = 1.0) -> TurnResponse:
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
    if mode in ("conversation", "scenario"):
        # Ripasso mirato: solo l'app lo vede, il benchmark usa modes.system_prompt senza questo blocco.
        system += modes.review_addendum(memory.review_context())
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
                res = await tts.speak(spoken, language, speed=tts_speed)
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


_HELP_SYSTEM_PROMPT = (
    "Sei un tutor paziente di inglese per un adulto italiano. Questa è una richiesta di aiuto fuori dal turno di pratica. "
    "Rispondi SOLO con un oggetto JSON valido con questa forma: "
    '{"segments": [{"lang": "it", "text": "..."}, {"lang": "en", "text": "..."}]}. '
    "Regole per i segmenti: "
    '- "lang" è "en" per OGNI parola, espressione o frase inglese, anche se breve (per esempio "would like", '
    '"I have some free time"). '
    '- "lang" è "it" per tutte le spiegazioni, le traduzioni e il resto del testo italiano. '
    "- I segmenti, concatenati nell'ordine, devono formare la risposta completa, con punteggiatura, spazi e a capo "
    '(usa "\\n" nel testo) già inclusi. Non duplicare testo e non aggiungere etichette. '
    "Contenuto: rispondi in italiano in modo chiaro e conciso, di solito entro 120 parole. Usa solo testo semplice: "
    "niente Markdown, asterischi, titoli, elenchi Markdown o formule LaTeX; per elencare forme grammaticali usa una riga "
    "semplice per forma. Spiega grammatica e lessico con esempi brevi in inglese seguiti dalla traduzione italiana. Se "
    "l'utente chiede come dire una frase, fornisci la frase inglese naturale e spiegala in italiano. Usa la conversazione "
    "precedente solo come contesto, non continuare il dialogo e non correggere questa domanda come esercizio. Non inventare "
    "informazioni personali dell'utente e non terminare con una nuova domanda."
)


async def contextual_help(*, session_id: str, text: str | None = None,
                          audio: bytes | None = None, audio_suffix: str = ".webm",
                          speak: bool = True, tts_speed: float = 1.0) -> HelpResponse:
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

    messages = [{"role": "system", "content": _HELP_SYSTEM_PROMPT},
                *memory.history(session_id, "conversation"),
                {"role": "user", "content": question}]
    t0 = time.perf_counter()
    answer, speech_parts, _ = await _help_answer(messages)
    timings["llm"] = round(time.perf_counter() - t0, 2)

    audio_b64 = audio_mime = None
    audio_segments: list[AudioClip] = []
    if speak and tts.enabled() and speech_parts:
        t0 = time.perf_counter()
        clips: list[AudioClip] = []
        for part, language in speech_parts:
            spoken = part.strip()
            if not spoken or not re.search(r"\w", spoken):
                continue
            try:
                res = await tts.speak(spoken, language, speed=tts_speed)
            except Exception as e:  # noqa: BLE001 - l'aiuto testuale resta disponibile se il TTS fallisce
                log.warning("TTS aiuto fallito (%s): %s", language, e)
                continue
            if res:
                clips.append(AudioClip(audio_b64=base64.b64encode(res[0]).decode(), audio_mime=res[1]))
        if clips:
            audio_b64, audio_mime = clips[0].audio_b64, clips[0].audio_mime
            audio_segments = clips[1:]
        timings["tts"] = round(time.perf_counter() - t0, 2)

    return HelpResponse(question=question, answer=answer, audio_b64=audio_b64,
                        audio_mime=audio_mime, audio_segments=audio_segments, timings=timings)
