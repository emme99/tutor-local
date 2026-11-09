"""Errori applicativi con uno stato HTTP associato.

I provider traducono gli errori di rete in queste eccezioni: così `main.py` può
restituire un messaggio utile senza dover indovinare quale servizio ha fallito.
"""
from __future__ import annotations


class TutorError(Exception):
    """Errore previsto dall'applicazione (non un bug)."""

    status_code = 500


class ServiceUnavailable(TutorError):
    """Un servizio locale (LLM/STT/TTS) non risponde o risponde male."""

    status_code = 502

    def __init__(self, service: str, detail: str):
        self.service = service
        super().__init__(f"{service}: {detail}")


class LLMUnavailable(ServiceUnavailable):
    def __init__(self, detail: str):
        super().__init__("LLM", detail)


class STTUnavailable(ServiceUnavailable):
    def __init__(self, detail: str):
        super().__init__("STT", detail)


class TTSUnavailable(ServiceUnavailable):
    def __init__(self, detail: str):
        super().__init__("TTS", detail)


class ModelOutputError(TutorError):
    """L'LLM ha risposto, ma non con il JSON del tutor."""

    status_code = 502


class EmptyAudio(TutorError):
    """L'audio è troppo breve o silenzioso per essere valutato."""

    status_code = 400


class AudioTooLong(TutorError):
    """L'audio supera la durata massima consentita per la valutazione."""

    status_code = 400
