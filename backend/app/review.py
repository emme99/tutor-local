"""Programmazione del ripasso (una versione semplice di SM-2).

``result``: 0 = non ricordato, 1 = difficile, 2 = bene, 3 = facile.
La funzione è pura: la persistenza e il calcolo di ``due`` restano in ``memory.py``.
"""
from __future__ import annotations

MIN_EASE = 1.3
MAX_EASE = 3.0
SOON_DAYS = 10 / (24 * 60)  # 10 minuti, per gli errori appena sbagliati


def schedule(result: int, interval_days: float = 0.0, ease: float = 2.5,
             repetitions: int = 0, lapses: int = 0) -> tuple[float, float, int, int]:
    """Ritorna (interval_days, ease, repetitions, lapses) dopo una valutazione."""
    result = max(0, min(3, int(result)))
    if result == 0:
        return SOON_DAYS, max(MIN_EASE, ease - 0.2), 0, lapses + 1

    repetitions += 1
    if result == 1:
        interval = 0.5 if repetitions == 1 else max(0.5, interval_days * 1.2)
        ease = max(MIN_EASE, ease - 0.15)
    elif result == 2:
        if repetitions == 1:
            interval = 1.0
        elif repetitions == 2:
            interval = 3.0
        else:
            interval = max(1.0, interval_days * ease)
    else:
        if repetitions == 1:
            interval = 2.0
        elif repetitions == 2:
            interval = 5.0
        else:
            interval = max(2.0, interval_days * ease * 1.2)
        ease = min(MAX_EASE, ease + 0.1)

    return round(interval, 4), round(ease, 3), repetitions, lapses


GRADE_LABELS = {0: "Non ricordato", 1: "Difficile", 2: "Bene", 3: "Facile"}
