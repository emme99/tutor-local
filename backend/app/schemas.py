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


class AudioClip(BaseModel):
    audio_b64: str
    audio_mime: str


class HelpResponse(BaseModel):
    question: str
    answer: str
    audio_b64: str | None = None
    audio_mime: str | None = None
    audio_segments: list[AudioClip] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)


class PronunciationDifference(BaseModel):
    expected: list[str]
    recognized: list[str]


class PronunciationCheck(BaseModel):
    expected: str
    transcript: str
    matched_words: int
    total_words: int
    differences: list[PronunciationDifference] = Field(default_factory=list)


class ReviewItem(BaseModel):
    id: int
    kind: str
    prompt: str
    answer: str
    hint: str = ""
    due: float
    interval_days: float
    ease: float
    repetitions: int
    lapses: int
    last_result: int | None = None


class ReviewQueue(BaseModel):
    items: list[ReviewItem] = Field(default_factory=list)
    due_count: int = 0
    total: int = 0


class ReviewStats(BaseModel):
    due_count: int = 0
    total: int = 0


class ReviewGradeIn(BaseModel):
    id: int
    result: int = Field(ge=0, le=3, description="0 = non ricordato, 1 = difficile, 2 = bene, 3 = facile")


class ReviewGradeOut(BaseModel):
    item: ReviewItem
    due_count: int
    total: int


class SessionSummary(BaseModel):
    session: str
    turns: int = 0
    modes: dict[str, int] = Field(default_factory=dict)
    corrections: list[Correction] = Field(default_factory=list)
    vocab: list[VocabItem] = Field(default_factory=list)
    started: float | None = None
    ended: float | None = None


class TurnResponse(BaseModel):
    session_id: str
    mode: str
    transcript: str
    tutor: TutorOutput
    audio_b64: str | None = None
    audio_mime: str | None = None
    explanations_audio_segments: list[AudioClip] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
