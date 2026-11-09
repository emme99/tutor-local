"""Valutazione fonetica della pronuncia: Wav2Vec2 XLSR-53 (CTC) su MPS.

L'IPA atteso viene da phonemizer (espeak), quello predetto dalla decodifica CTC
dell'audio a 16 kHz. Il tokenizer del modello (`Wav2Vec2PhonemeCTCTokenizer`)
espone `phonemize()` e separa già i singoli fonemi: si usa quello invece di
spezzare a mano l'IPA, perché il greedy longest-match confonde token come
`ju`/`uː` e produce sequenze sbagliate.

Il confronto è una distanza di Levenshtein pesata sui simboli IPA: una
sostituzione tra due vocali costa 0.5, tutto il resto 1. Così le differenze di
qualità vocalica dovute all'accento (ɹ→r, ʊ→u, ...) pesano meno degli errori
consonantici (θ→t, ð→d) e delle parole mancanti. La lunghezza (`ː`) e gli
allofoni noti (ɹ/ɾ/ᵻ/ɐ) sono normalizzati prima del confronto.

Modello e processor sono caricati alla prima chiamata (come mlx-whisper in
providers/stt.py): import, download e memoria non pesano sull'avvio del backend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import unicodedata
import wave

from .config import settings
from .errors import EmptyAudio
from .providers import stt

logger = logging.getLogger("tutor")

# phonemizer/espeak: "en" -> "en-us", "it" -> "it"
_LANG_CODES = {"en": "en-us", "it": "it"}

# Simboli che il modello può scrivere diversamente da phonemizer ma che
# rappresentano lo stesso fonema (o un allofono accettabile in inglese).
_ALLOPHONES = {"ɹ": "r", "ɾ": "t", "ᵻ": "ɪ", "ɐ": "ə"}
_LENGTH_MARKS = ("ː", "ˑ")
_VOWELS = frozenset("aeiouɑɒɔɛɜɝəɪʊʌæɐɚᵻɨɯɵøœɶɞɘɤʉ")
VOWEL_SUBSTITUTION_COST = 0.5

_lock = asyncio.Lock()  # una sola operazione alla volta (caricamento del modello e inferenza)
_state: dict | None = None


def _device() -> str:
    import torch

    requested = (settings.phonetic_device or "mps").strip().lower()
    if requested == "mps" and not (torch.backends.mps.is_built() and torch.backends.mps.is_available()):
        logger.warning("MPS non disponibile: motore fonetico su CPU")
        return "cpu"
    return requested


def _load() -> dict:
    """Carica processor, modello e tokenizer (una volta sola)."""
    import torch
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

    device = _device()
    model_id = settings.phonetic_model
    try:
        processor = Wav2Vec2Processor.from_pretrained(model_id)
        model = Wav2Vec2ForCTC.from_pretrained(model_id).to(torch.device(device)).eval()
    except Exception as e:  # checkpoint mancante, download fallito, espeak-ng assente
        raise RuntimeError(f"motore fonetico non disponibile ({model_id} su {device}): {e}") from e
    logger.info("motore fonetico pronto: %s su %s", model_id, device)
    return {"processor": processor, "tokenizer": processor.tokenizer,
            "model": model, "device": device}


async def _get_state() -> dict:
    global _state
    if _state is None:
        async with _lock:
            if _state is None:
                _state = await asyncio.to_thread(_load)
    return _state


# --- Funzioni pure (testabili senza modello) ---------------------------------

def normalize(tokens: list[str]) -> list[str]:
    """Normalizzazione Unicode (NFC) dei token e rimozione dei vuoti."""
    return [token for token in (unicodedata.normalize("NFC", t) for t in tokens) if token.strip()]


def canonical(token: str) -> str:
    """Toglie i segni di lunghezza e mappa gli allofoni noti sullo stesso simbolo."""
    token = unicodedata.normalize("NFC", token)
    for mark in _LENGTH_MARKS:
        token = token.replace(mark, "")
    return "".join(_ALLOPHONES.get(symbol, symbol) for symbol in token)


def ipa_symbols(tokens: list[str]) -> list[str]:
    """Sequenza atomica di simboli IPA (un simbolo per carattere, normalizzato)."""
    return [symbol for token in tokens for symbol in canonical(token) if not symbol.isspace()]


def is_vowel(symbol: str) -> bool:
    return symbol in _VOWELS


def distance(expected: list[str], predicted: list[str]) -> float:
    """Levenshtein pesato: sostituzione vocale-vocale = 0.5, il resto = 1."""
    previous = [float(j) for j in range(len(predicted) + 1)]
    for i, x in enumerate(expected, 1):
        current = [float(i)]
        for j, y in enumerate(predicted, 1):
            if x == y:
                substitution = 0.0
            elif is_vowel(x) and is_vowel(y):
                substitution = VOWEL_SUBSTITUTION_COST
            else:
                substitution = 1.0
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + substitution))
        previous = current
    return previous[-1]


def score(expected: list[str], predicted: list[str]) -> int:
    """Accuratezza 0-100 (100 = sequenza identica, 0 = nessun simbolo atteso)."""
    if not expected:
        return 0
    return round(max(0.0, 1 - distance(expected, predicted) / len(expected)) * 100)


# --- Audio e inferenza --------------------------------------------------------

def _prepare_wav(audio: bytes, suffix: str) -> str:
    """ffmpeg -> WAV 16 kHz mono; scarta audio breve/silenzioso (stesse soglie di Whisper)."""
    wav = stt.to_wav(audio, suffix)
    duration, rms = stt.audio_stats(wav)
    if duration < settings.audio_min_seconds or rms < settings.audio_min_rms:
        os.unlink(wav)
        raise EmptyAudio("non ho sentito nulla: riprova")
    return wav


def _read_wav(wav_path: str):
    import numpy as np

    with wave.open(wav_path, "rb") as w:
        rate, raw = w.getframerate(), w.readframes(w.getnframes())
    if rate != 16000:
        raise RuntimeError(f"campionamento inatteso: {rate} Hz (atteso 16000)")
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _decode(wav_path: str, state: dict) -> list[str]:
    """Token IPA predetti dal modello per un WAV 16 kHz."""
    import torch

    processor, model = state["processor"], state["model"]
    inputs = processor(_read_wav(wav_path), sampling_rate=16000, return_tensors="pt")
    with torch.inference_mode():
        logits = model(inputs.input_values.to(state["device"])).logits
    return normalize(processor.batch_decode(logits.argmax(dim=-1))[0].split())


def _text_ipa(text: str, lang: str, state: dict) -> list[str]:
    """Token IPA attesi del testo, con i confini di fonema corretti del tokenizer."""
    try:
        code = _LANG_CODES[lang]
    except KeyError:
        raise ValueError(f"lingua non supportata: {lang!r}") from None
    tokenizer = state["tokenizer"]
    word_delimiter = tokenizer.word_delimiter_token
    tokens = tokenizer.phonemize(text, code).split(" ")
    return normalize([token for token in tokens if token and token != word_delimiter])


# --- API pubblica -------------------------------------------------------------

async def text_to_ipa(text: str, lang: str = "en") -> list[str]:
    """IPA atteso del testo (token normalizzati), pronto per il confronto."""
    state = await _get_state()
    async with _lock:
        tokens = await asyncio.to_thread(_text_ipa, text, lang, state)
    return [canonical(token) for token in tokens]


async def audio_to_phonemes(audio: bytes, suffix: str = ".webm") -> list[str]:
    """Token IPA predetti dall'audio dell'allievo (normalizzati)."""
    wav = await asyncio.to_thread(_prepare_wav, audio, suffix)
    try:
        state = await _get_state()
        async with _lock:
            tokens = await asyncio.to_thread(_decode, wav, state)
    finally:
        os.unlink(wav)
    return [canonical(token) for token in tokens]


async def evaluate_pronunciation(target: str, audio: bytes, lang: str = "en",
                                 suffix: str = ".webm") -> dict:
    """Confronta la ripetizione con la frase attesa: score 0-100 e sequenze IPA."""
    wav = await asyncio.to_thread(_prepare_wav, audio, suffix)
    try:
        state = await _get_state()
        async with _lock:
            expected_tokens = await asyncio.to_thread(_text_ipa, target, lang, state)
            predicted_tokens = await asyncio.to_thread(_decode, wav, state)
    finally:
        os.unlink(wav)
    expected, predicted = ipa_symbols(expected_tokens), ipa_symbols(predicted_tokens)
    value = score(expected, predicted)
    total_phones = len(expected_tokens)
    return {
        "expected": target,
        "score": value,
        "matched_phones": round(total_phones * value / 100),
        "total_phones": total_phones,
        "expected_ipa": " ".join(canonical(token) for token in expected_tokens),
        "predicted_ipa": " ".join(canonical(token) for token in predicted_tokens),
    }
