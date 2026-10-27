"""TTS: endpoint OpenAI-compatible /audio/speech. Facoltativo: senza TTS_BASE_URL l'app risponde solo con il testo."""
from __future__ import annotations

import httpx

from ..config import settings

_client: httpx.AsyncClient | None = None


def enabled() -> bool:
    return bool(settings.tts_base_url)


async def speak(text: str, lang: str) -> tuple[bytes, str] | None:
    global _client
    if not enabled() or not text.strip():
        return None
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))
    voice = settings.tts_voice_en if lang == "en" else settings.tts_voice_it
    r = await _client.post(
        settings.tts_base_url.rstrip("/") + "/audio/speech",
        json={"model": settings.tts_model, "input": text, "voice": voice, "language": lang,
              "response_format": settings.tts_format},
        headers={"Authorization": f"Bearer {settings.tts_api_key}"},
    )
    r.raise_for_status()
    mime = r.headers.get("content-type", "audio/mpeg").split(";")[0]
    return r.content, mime
