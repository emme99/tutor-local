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
from .errors import AudioTooLong, EmptyAudio
from .phonetic_tips import get_issues
from .providers import stt

logger = logging.getLogger("tutor")

# phonemizer/espeak: "en" -> "en-us", "it" -> "it"
_LANG_CODES = {"en": "en-us", "it": "it"}

# Simboli che il modello può scrivere diversamente da phonemizer ma che
# rappresentano lo stesso fonema (o un allofono accettabile in inglese).
_ALLOPHONES = {"ɹ": "r", "ɾ": "t", "ᵻ": "ɪ", "ɐ": "ə"}
_LENGTH_MARKS = ("ː", "ˑ")
_VOWELS = frozenset("aeiouɑɒɔɛɜɝəɪʊʌæɐɚᵻɨɯɵøœɶɞɘɤʉ")
DIPHTHONGS = frozenset({"oʊ", "aɪ", "eɪ", "aʊ", "ɔɪ"})
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


def split_units(canonical_token: str) -> list[str]:
    """Separa il token nei suoi simboli atomici, preservando i dittonghi come unità."""
    units: list[str] = []
    i = 0
    s = canonical_token
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        if i + 1 < len(s) and s[i:i + 2] in DIPHTHONGS:
            units.append(s[i:i + 2])
            i += 2
        else:
            units.append(s[i])
            i += 1
    return units


def ipa_symbols(tokens: list[str]) -> list[str]:
    """Sequenza di unità IPA (un simbolo o dittongo per unità, normalizzato)."""
    return [u for token in tokens for u in split_units(canonical(token))]


def is_vowel(symbol: str) -> bool:
    return symbol in _VOWELS or symbol in DIPHTHONGS


def align(expected: list[str], predicted: list[str]) -> list[dict]:
    """Allineamento dinamico Levenshtein pesato con backtrace.

    Restituisce operazioni match | sub | ins | del con indici e costo.
    """
    n, m = len(expected), len(predicted)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = float(i)
    for j in range(1, m + 1):
        dp[0][j] = float(j)

    for i in range(1, n + 1):
        x = expected[i - 1]
        for j in range(1, m + 1):
            y = predicted[j - 1]
            if x == y:
                sub = 0.0
            elif is_vowel(x) and is_vowel(y):
                sub = VOWEL_SUBSTITUTION_COST
            else:
                sub = 1.0
            dp[i][j] = min(dp[i - 1][j] + 1.0, dp[i][j - 1] + 1.0, dp[i - 1][j - 1] + sub)

    i, j = n, m
    ops: list[dict] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            x, y = expected[i - 1], predicted[j - 1]
            if x == y:
                sub = 0.0
            elif is_vowel(x) and is_vowel(y):
                sub = VOWEL_SUBSTITUTION_COST
            else:
                sub = 1.0
            if abs(dp[i][j] - (dp[i - 1][j - 1] + sub)) < 1e-6:
                op_type = "match" if x == y else "sub"
                ops.append({
                    "op": op_type,
                    "expected": x,
                    "heard": y,
                    "cost": sub,
                    "expected_idx": i - 1,
                    "predicted_idx": j - 1,
                })
                i -= 1
                j -= 1
                continue
        if i > 0 and abs(dp[i][j] - (dp[i - 1][j] + 1.0)) < 1e-6:
            ops.append({
                "op": "del",
                "expected": expected[i - 1],
                "heard": None,
                "cost": 1.0,
                "expected_idx": i - 1,
                "predicted_idx": None,
            })
            i -= 1
        elif j > 0 and abs(dp[i][j] - (dp[i][j - 1] + 1.0)) < 1e-6:
            ops.append({
                "op": "ins",
                "expected": None,
                "heard": predicted[j - 1],
                "cost": 1.0,
                "expected_idx": None,
                "predicted_idx": j - 1,
            })
            j -= 1
        else:
            raise RuntimeError(f"Backtrace error at {i}, {j}")
    ops.reverse()
    return ops


def distance(expected: list[str], predicted: list[str]) -> float:
    """Levenshtein pesato calcolato dall'allineamento ottimo."""
    return sum(op["cost"] for op in align(expected, predicted))


def score(expected: list[str], predicted: list[str]) -> int:
    """Accuratezza 0-100 (100 = sequenza identica, 0 = nessun simbolo atteso)."""
    if not expected:
        return 0
    return round(max(0.0, 1 - distance(expected, predicted) / len(expected)) * 100)


def verdict(ops: list[dict]) -> str:
    """Verdetto qualitativo per bersagli brevi: ok, dubbio, da_rivedere."""
    differences = [op for op in ops if op["op"] != "match"]
    if not differences:
        return "ok"
    for op in differences:
        if op["op"] in ("ins", "del"):
            return "da_rivedere"
        exp, hrd = op["expected"], op["heard"]
        if exp is None or hrd is None or not (is_vowel(exp) and is_vowel(hrd)):
            return "da_rivedere"
    return "dubbio"


# --- Audio e inferenza --------------------------------------------------------

def _prepare_wav(audio: bytes, suffix: str) -> str:
    """ffmpeg -> WAV 16 kHz mono; scarta audio breve/silenzioso o troppo lungo."""
    wav = stt.to_wav(audio, suffix)
    duration, rms = stt.audio_stats(wav)
    if duration < settings.audio_min_seconds or rms < settings.audio_min_rms:
        os.unlink(wav)
        raise EmptyAudio("non ho sentito nulla: riprova")
    if duration > settings.phonetic_max_seconds:
        os.unlink(wav)
        raise AudioTooLong(f"audio troppo lungo ({duration:.1f} s > {settings.phonetic_max_seconds:.0f} s): registra solo la frase richiesta")
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


def _text_ipa_words(text: str, lang: str, state: dict) -> tuple[list[str], list[dict]]:
    """Tokenizza e fonemizza parola per parola, mantenendo la mappa fonema -> parola."""
    try:
        code = _LANG_CODES[lang]
    except KeyError:
        raise ValueError(f"lingua non supportata: {lang!r}") from None
    tokenizer = state["tokenizer"]
    word_delimiter = tokenizer.word_delimiter_token

    words = text.split()
    all_units: list[str] = []
    word_data: list[dict] = []

    for w in words:
        raw = tokenizer.phonemize(w, code).split(" ")
        tokens = normalize([token for token in raw if token and token != word_delimiter])
        w_units = ipa_symbols(tokens)
        word_data.append({"word": w, "units": w_units})
        all_units.extend(w_units)

    return all_units, word_data


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
    """IPA atteso del testo (unità normalizzate), pronto per il confronto."""
    state = await _get_state()
    async with _lock:
        tokens = await asyncio.to_thread(_text_ipa, text, lang, state)
    return ipa_symbols(tokens)


async def audio_to_phonemes(audio: bytes, suffix: str = ".webm") -> list[str]:
    """Token IPA predetti dall'audio dell'allievo (unità normalizzate)."""
    wav = await asyncio.to_thread(_prepare_wav, audio, suffix)
    try:
        state = await _get_state()
        async with _lock:
            tokens = await asyncio.to_thread(_decode, wav, state)
    finally:
        os.unlink(wav)
    return ipa_symbols(tokens)


async def evaluate_pronunciation(target: str, audio: bytes, lang: str = "en",
                                 suffix: str = ".webm") -> dict:
    """Confronta la ripetizione con la frase attesa: score 0-100, parole, allineamento e verdetto."""
    wav = await asyncio.to_thread(_prepare_wav, audio, suffix)
    try:
        state = await _get_state()
        async with _lock:
            expected_units, word_data = await asyncio.to_thread(_text_ipa_words, target, lang, state)
            predicted_tokens = await asyncio.to_thread(_decode, wav, state)
    finally:
        os.unlink(wav)

    predicted_units = ipa_symbols(predicted_tokens)
    ops = align(expected_units, predicted_units)

    # Mappa simbolo -> parola
    unit_to_word: list[int] = []
    for w_idx, wd in enumerate(word_data):
        for _ in wd["units"]:
            unit_to_word.append(w_idx)

    # Attribuisci ogni operazione a una parola attesa
    op_word_indices: list[int | None] = []
    last_w_idx: int | None = None
    for op in ops:
        if op["expected_idx"] is not None and op["expected_idx"] < len(unit_to_word):
            w_idx = unit_to_word[op["expected_idx"]]
            op_word_indices.append(w_idx)
            last_w_idx = w_idx
        else:
            op_word_indices.append(last_w_idx)

    first_valid = 0
    for w_idx in op_word_indices:
        if w_idx is not None:
            first_valid = w_idx
            break
    resolved_word_indices = [first_valid if w_idx is None else w_idx for w_idx in op_word_indices]

    words: list[dict] = []
    for w_idx, wd in enumerate(word_data):
        w_ops = [ops[k] for k, assigned in enumerate(resolved_word_indices) if assigned == w_idx]
        w_units = wd["units"]
        w_exp_ipa = " ".join(w_units)
        w_heard_ipa = " ".join(op["heard"] for op in w_ops if op["heard"] is not None)
        w_cost = sum(op["cost"] for op in w_ops)
        w_score = round(max(0.0, 1 - w_cost / len(w_units)) * 100) if w_units else 100
        words.append({
            "word": wd["word"],
            "expected_ipa": w_exp_ipa,
            "heard_ipa": w_heard_ipa,
            "score": w_score,
            "ops": [{"op": op["op"], "expected": op["expected"], "heard": op["heard"]} for op in w_ops],
        })

    total_cost = sum(op["cost"] for op in ops)
    total_phones = len(expected_units)
    value = round(max(0.0, 1 - total_cost / total_phones) * 100) if total_phones else 0
    matched_phones = sum(1 for op in ops if op["op"] == "match")
    short_target = total_phones <= settings.phonetic_short_max_units
    v = verdict(ops) if short_target else None

    issues = get_issues(ops, word_data, unit_to_word)

    return {
        "expected": target,
        "score": value,
        "matched_phones": matched_phones,
        "total_phones": total_phones,
        "expected_ipa": " ".join(expected_units),
        "predicted_ipa": " ".join(predicted_units),
        "short_target": short_target,
        "verdict": v,
        "ops": [{"op": op["op"], "expected": op["expected"], "heard": op["heard"]} for op in ops],
        "words": words,
        "issues": issues,
    }
