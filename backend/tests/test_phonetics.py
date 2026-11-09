"""Test delle funzioni pure del motore fonetico (senza modello né audio)."""
from app.phonetics import canonical, distance, ipa_symbols, is_vowel, normalize, score


def test_canonical_strips_length_and_maps_allophones():
    assert canonical("ɔːɹ") == "ɔr"
    assert canonical("ɹ") == "r"
    assert canonical("ɾ") == "t"
    assert canonical("ᵻ") == "ɪ"
    assert canonical("ɐ") == "ə"
    assert canonical("aɪ") == "aɪ"


def test_ipa_symbols_flattens_tokens():
    assert ipa_symbols(["tʃ", "aɪ", " ", ""]) == ["t", "ʃ", "a", "ɪ"]


def test_is_vowel():
    assert is_vowel("a") and is_vowel("ɪ") and is_vowel("ə")
    assert not is_vowel("t") and not is_vowel("ʃ")


def test_distance_exact_and_edits():
    assert distance([], []) == 0
    assert distance(["a", "b"], ["a", "b"]) == 0
    assert distance(["a", "b"], ["a", "c"]) == 1  # sostituzione tra consonanti
    assert distance(["a", "b"], ["a"]) == 1       # cancellazione
    assert distance(["a"], ["a", "b"]) == 1       # inserimento


def test_distance_vowel_substitution_costs_less():
    assert distance(["a"], ["e"]) == 0.5
    assert distance(["ɪ"], ["i"]) == 0.5
    assert distance(["a"], ["t"]) == 1.0


def test_score_is_percentage_of_expected_symbols():
    assert score(["a", "b"], ["a", "b"]) == 100
    assert score(["a", "b"], ["a", "t"]) == 50
    assert score(["a", "b"], []) == 0
    assert score([], []) == 0


def test_normalize_removes_empty_tokens():
    assert normalize(["a", " ", ""]) == ["a"]
