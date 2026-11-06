from __future__ import annotations

from pydantic import BaseModel, Field


class Correction(BaseModel):
    original: str = ""
    corrected: str = ""
    explanation_it: str = ""
    type: str = "grammar"


class VocabItem(BaseModel):
    term: str
    translation_it: str = ""
    example: str = ""


class TutorOutput(BaseModel):
    is_correct: bool = True
    corrected_sentence: str = ""
    corrections: list[Correction] = Field(default_factory=list)
    reply: str = ""
    suggested_reply: str = ""
    new_vocab: list[VocabItem] = Field(default_factory=list)
    follow_up: str = ""


class HelpResponse(BaseModel):
    question: str
    answer: str
    audio_b64: str | None = None
    audio_mime: str | None = None
    timings: dict[str, float] = Field(default_factory=dict)


class AudioClip(BaseModel):
    audio_b64: str
    audio_mime: str


class PronunciationDifference(BaseModel):
    expected: list[str]
    recognized: list[str]


class PronunciationCheck(BaseModel):
    expected: str
    transcript: str
    matched_words: int
    total_words: int
    differences: list[PronunciationDifference] = Field(default_factory=list)


class TurnResponse(BaseModel):
    session_id: str
    mode: str
    transcript: str
    tutor: TutorOutput
    audio_b64: str | None = None
    audio_mime: str | None = None
    explanations_audio_segments: list[AudioClip] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
