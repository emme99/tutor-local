"""Estrazione robusta di un oggetto JSON dall'output di un LLM (senza dipendenze)."""
import json
import re


class NotJSON(ValueError):
    pass


def extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise NotJSON("nessun oggetto JSON nella risposta") from None
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise NotJSON(str(e)) from None
    if not isinstance(obj, dict):
        raise NotJSON("il JSON non è un oggetto")
    return obj
