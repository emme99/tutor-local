from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schemas import PronunciationCheck, PronunciationDifference


def _words(text: str) -> list[str]:
    normalized = text.casefold().replace("’", "'")
    return re.findall(r"[a-z]+(?:'[a-z]+)*|\d+", normalized)


def compare_transcript(expected: str, transcript: str) -> PronunciationCheck:
    expected_words = _words(expected)
    recognized_words = _words(transcript)
    matcher = SequenceMatcher(a=expected_words, b=recognized_words, autojunk=False)
    matched_words = 0
    differences: list[PronunciationDifference] = []

    for operation, expected_start, expected_end, recognized_start, recognized_end in matcher.get_opcodes():
        if operation == "equal":
            matched_words += expected_end - expected_start
        else:
            differences.append(PronunciationDifference(
                expected=expected_words[expected_start:expected_end],
                recognized=recognized_words[recognized_start:recognized_end],
            ))

    return PronunciationCheck(
        expected=expected,
        transcript=transcript,
        matched_words=matched_words,
        total_words=len(expected_words),
        differences=differences,
    )