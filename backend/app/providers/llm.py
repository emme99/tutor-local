"""Client LLM per qualsiasi endpoint OpenAI-compatible."""
from __future__ import annotations

import httpx
from pydantic import ValidationError

from ..config import settings
from ..jsonparse import NotJSON, extract_json
from ..schemas import TutorOutput

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0))
    return _client


async def chat(messages: list[dict], *, base_url: str | None = None, model: str | None = None,
               api_key: str | None = None, json_mode: bool | None = None,
               extra_body: dict | None = None, temperature: float | None = None,
               max_tokens: int | None = None) -> tuple[str, dict]:
    """Una chiamata chat/completions non in streaming. Ritorna (testo, usage)."""
    payload: dict = {
        "model": model or settings.llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature if temperature is None else temperature,
        "max_tokens": max_tokens or settings.llm_max_tokens,
        "stream": False,
    }
    if settings.llm_json_mode if json_mode is None else json_mode:
        payload["response_format"] = {"type": "json_object"}
    payload.update(settings.llm_extra_body if extra_body is None else extra_body)

    url = (base_url or settings.llm_base_url).rstrip("/") + "/chat/completions"
    r = await _http().post(url, json=payload,
                           headers={"Authorization": f"Bearer {api_key or settings.llm_api_key}"})
    r.raise_for_status()
    data = r.json()
    choice = data["choices"][0]
    msg = choice["message"]
    usage = dict(data.get("usage") or {})
    usage["finish_reason"] = choice.get("finish_reason")
    # alcuni server restituiscono il ragionamento in un campo separato dal contenuto
    usage["reasoning_chars"] = len(msg.get("reasoning") or msg.get("reasoning_content") or "")
    return msg.get("content") or "", usage


def parse_tutor(text: str) -> TutorOutput:
    return TutorOutput.model_validate(extract_json(text))


async def tutor_reply(system: str, history: list[dict], user_text: str, **kw) -> tuple[TutorOutput, dict]:
    """Chiede il JSON del tutor; se la risposta non è valida, riprova una volta."""
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_text}]
    text, usage = await chat(messages, **kw)
    try:
        return parse_tutor(text), usage
    except (NotJSON, ValidationError):
        if usage.get("finish_reason") == "length":
            raise NotJSON("risposta troncata da max_tokens: probabile thinking attivo (usa reasoning_effort=none)") from None
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Reply again with ONLY the JSON object, no other text."}]
        text, usage2 = await chat(messages, **kw)
        usage = {k: (usage.get(k) or 0) + (usage2.get(k) or 0) for k in ("prompt_tokens", "completion_tokens")}
        return parse_tutor(text), usage
