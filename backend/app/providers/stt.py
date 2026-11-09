"""STT: Whisper (large-v3-turbo) in-process con MLX oppure un endpoint OpenAI-compatible.

Il browser invia webm/mp4: ffmpeg lo converte in WAV 16 kHz mono. Prima di trascrivere si scartano gli audio troppo
brevi o silenziosi, perché Whisper su silenzio tende a inventare frasi ("Thank you.", "Grazie.").
"""
from __future__ import annotations

import array
import asyncio
import math
import os
import subprocess
import sys
import tempfile
import wave

from ..config import settings
from ..errors import STTUnavailable


def to_wav(data: bytes, suffix: str = ".webm") -> str:
    """Converte un audio del browser (webm/mp4/...) in WAV 16 kHz mono 16 bit."""
    src = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    src.write(data)
    src.close()
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out.close()
    try:
        p = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src.name,
                            "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", out.name], capture_output=True)
        if p.returncode != 0:
            raise RuntimeError("ffmpeg: " + p.stderr.decode(errors="ignore")[:300])
        return out.name
    except FileNotFoundError:
        raise RuntimeError("ffmpeg non trovato (brew install ffmpeg)") from None
    finally:
        os.unlink(src.name)


def audio_stats(wav_path: str) -> tuple[float, float]:
    """(durata in secondi, RMS normalizzato 0..1) di un WAV PCM a 16 bit."""
    with wave.open(wav_path, "rb") as w:
        n, rate, raw = w.getnframes(), w.getframerate(), w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples or not rate:
        return 0.0, 0.0
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768
    return n / rate, rms


def _transcribe_mlx(wav: str, language: str | None) -> str:
    import mlx_whisper

    kw = {"initial_prompt": settings.stt_initial_prompt} if settings.stt_initial_prompt else {}
    out = mlx_whisper.transcribe(wav, path_or_hf_repo=settings.stt_model, language=language,
                                 condition_on_previous_text=False, **kw)
    return out["text"].strip()


async def _transcribe_openai(wav: str, language: str | None) -> str:
    import httpx

    if not settings.stt_base_url:
        raise RuntimeError("STT_BACKEND=openai richiede STT_BASE_URL")
    data = {"model": settings.stt_api_model, "response_format": "json"}
    if language:
        data["language"] = language
    if settings.stt_initial_prompt:
        data["prompt"] = settings.stt_initial_prompt
    with open(wav, "rb") as f:
        content = f.read()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as c:
            r = await c.post(settings.stt_base_url.rstrip("/") + "/audio/transcriptions",
                             headers={"Authorization": f"Bearer {settings.stt_api_key}"},
                             data=data, files={"file": ("audio.wav", content, "audio/wav")})
            r.raise_for_status()
            return r.json()["text"].strip()
    except httpx.TimeoutException as e:
        raise STTUnavailable(f"nessuna risposta da {settings.stt_base_url}") from e
    except httpx.HTTPStatusError as e:
        raise STTUnavailable(f"ha risposto {e.response.status_code}: {e.response.text[:200]}") from e
    except httpx.HTTPError as e:
        raise STTUnavailable(str(e)) from e
    except (KeyError, ValueError) as e:
        raise STTUnavailable(f"risposta non valida: {e}") from e


async def transcribe(audio: bytes, language: str | None, suffix: str = ".webm") -> str:
    """Ritorna il testo, oppure "" se l'audio è troppo breve/silenzioso."""
    wav = await asyncio.to_thread(to_wav, audio, suffix)
    try:
        duration, rms = audio_stats(wav)
        if duration < settings.audio_min_seconds or rms < settings.audio_min_rms:
            return ""
        if settings.stt_backend == "openai":
            return await _transcribe_openai(wav, language)
        async with _lock:  # un solo lavoro alla volta sulla GPU: le richieste concorrenti si accodano
            return await asyncio.to_thread(_transcribe_mlx, wav, language)
    finally:
        os.unlink(wav)


_lock = asyncio.Lock()
