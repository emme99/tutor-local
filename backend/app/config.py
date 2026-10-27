"""Configurazione da variabili d'ambiente (o file .env nella cartella backend/ o nella radice)."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    load_dotenv(root / "backend" / ".env")
except ImportError:  # python-dotenv è opzionale
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _json_env(name: str, default: dict) -> dict:
    raw = _env(name, "").strip()
    return json.loads(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    # LLM (qualsiasi endpoint OpenAI-compatible: Ollama, LM Studio, mlx_lm.server, llama-server)
    llm_base_url: str = _env("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_model: str = _env("LLM_MODEL", "gemma4:26b")
    llm_api_key: str = _env("LLM_API_KEY", "local")
    llm_temperature: float = float(_env("LLM_TEMPERATURE", "0.4"))
    llm_max_tokens: int = int(_env("LLM_MAX_TOKENS", "700"))
    llm_json_mode: bool = _env("LLM_JSON_MODE", "1") == "1"
    # "reasoning_effort: none" spegne il thinking su Ollama (/v1) e su Splash. Con LLM_EXTRA_BODY={} lo lasci acceso.
    llm_extra_body: dict = field(default_factory=lambda: _json_env("LLM_EXTRA_BODY", {"reasoning_effort": "none"}))

    # STT: "mlx" = Whisper in-process su Apple Silicon; "openai" = endpoint OpenAI-compatible /audio/transcriptions
    stt_backend: str = _env("STT_BACKEND", "mlx")
    stt_model: str = _env("STT_MODEL", "mlx-community/whisper-large-v3-turbo")      # backend mlx
    stt_base_url: str = _env("STT_BASE_URL", "")                                     # backend openai
    stt_api_key: str = _env("STT_API_KEY", "local")
    stt_api_model: str = _env("STT_API_MODEL", "whisper-1")
    stt_initial_prompt: str = _env("STT_INITIAL_PROMPT", "")
    # Audio troppo breve o silenzioso non va a Whisper (altrimenti inventa testo tipo "Thank you.")
    audio_min_seconds: float = float(_env("AUDIO_MIN_SECONDS", "0.4"))
    audio_min_rms: float = float(_env("AUDIO_MIN_RMS", "0.004"))

    # TTS: endpoint OpenAI-compatible /audio/speech (es. il tuo openai-macos-stt-tts). Vuoto = nessun audio.
    tts_base_url: str = _env("TTS_BASE_URL", "")
    tts_api_key: str = _env("TTS_API_KEY", "local")
    tts_model: str = _env("TTS_MODEL", "tts-1")
    tts_voice_en: str = _env("TTS_VOICE_EN", "alloy")
    tts_voice_it: str = _env("TTS_VOICE_IT", "alloy")
    tts_format: str = _env("TTS_FORMAT", "mp3")

    db_path: str = _env("DB_PATH", str(Path(__file__).resolve().parents[2] / "data" / "tutor.db"))
    history_turns: int = int(_env("HISTORY_TURNS", "6"))


settings = Settings()
