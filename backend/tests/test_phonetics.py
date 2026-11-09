"""Test delle funzioni pure del motore fonetico (senza modello né audio)."""
from app.config import settings
from app.phonetics import (
    align,
    canonical,
    distance,
    ipa_symbols,
    is_vowel,
    normalize,
    score,
    verdict,
)


def test_canonical_strips_length_and_maps_allophones():
    assert canonical("ɔːɹ") == "ɔr"
    assert canonical("ɹ") == "r"
    assert canonical("ɾ") == "t"
    assert canonical("ᵻ") == "ɪ"
    assert canonical("ɐ") == "ə"
    assert canonical("aɪ") == "aɪ"


def test_ipa_symbols_preserves_diphthongs():
    assert ipa_symbols(["tʃ", "aɪ", " ", ""]) == ["t", "ʃ", "aɪ"]
    assert ipa_symbols(["oʊ", "k eɪ"]) == ["oʊ", "k", "eɪ"]


def test_is_vowel():
    assert is_vowel("a") and is_vowel("ɪ") and is_vowel("ə")
    assert is_vowel("oʊ") and is_vowel("aɪ") and is_vowel("eɪ")
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
    assert distance(["oʊ"], ["o"]) == 0.5          # monottongazione = sostituzione vocalica
    assert distance(["aɪ"], ["eɪ"]) == 0.5         # scambio tra dittonghi = 0.5
    assert distance(["oʊ"], ["t"]) == 1.0          # dittongo -> consonante = 1.0


def test_score_is_percentage_of_expected_symbols():
    assert score(["a", "b"], ["a", "b"]) == 100
    assert score(["a", "b"], ["a", "t"]) == 50
    assert score(["a", "b"], []) == 0
    assert score([], []) == 0


def test_normalize_removes_empty_tokens():
    assert normalize(["a", " ", ""]) == ["a"]


def test_align_exact_and_verdict():
    ops = align(["ʃ", "ɪ", "p"], ["ʃ", "ɪ", "p"])
    assert len(ops) == 3
    assert all(op["op"] == "match" for op in ops)
    assert verdict(ops) == "ok"


def test_align_ship_sheep_vowel_diff():
    ops = align(["ʃ", "ɪ", "p"], ["ʃ", "i", "p"])
    assert len(ops) == 3
    assert ops[1]["op"] == "sub" and ops[1]["cost"] == 0.5
    assert verdict(ops) == "dubbio"


def test_align_think_sink_consonant_diff():
    ops = align(["θ", "ɪ", "ŋ", "k"], ["s", "ɪ", "ŋ", "k"])
    assert ops[0]["op"] == "sub" and ops[0]["cost"] == 1.0
    assert verdict(ops) == "da_rivedere"


def test_align_towel_tabol_case():
    expected = ["t", "aʊ", "ə", "l"]
    predicted = ["t", "a", "b", "ɔ", "l"]
    ops = align(expected, predicted)
    assert verdict(ops) == "da_rivedere"


def test_align_insertion_street_istreet():
    expected = ["s", "t", "r", "i", "t"]
    predicted = ["ɪ", "s", "t", "r", "i", "t"]
    ops = align(expected, predicted)
    assert ops[0]["op"] == "ins" and ops[0]["heard"] == "ɪ"
    assert verdict(ops) == "da_rivedere"


def test_align_deletion_omitted_word():
    ops = align(["a", "b"], [])
    assert all(op["op"] == "del" for op in ops)
    assert verdict(ops) == "da_rivedere"


def test_align_en02_values():
    exp_tokens = "t ə m ɑ r oʊ m ɔr n ɪ ŋ aɪ h æ v ə m i t ɪ ŋ w ɪ ð ð ə k l aɪə n t s oʊ aɪ n i d t ə w eɪ k ʌ p ɜ l i".split()
    pred_tokens = "t ʊ m ɔ r o m ɔ n ɪ ŋ aɪ h æ v m i t ɪ ŋ w ɪ d ð ɚ k l aɪ ə n t s o aɪ n i d t ʊ w eɪ k a p eɪ r l i".split()

    exp_units = ipa_symbols(exp_tokens)
    pred_units = ipa_symbols(pred_tokens)

    assert len(exp_units) == 49
    d = distance(exp_units, pred_units)
    assert d == 8.0
    s = score(exp_units, pred_units)
    assert s == 84


def test_verdict_short_target_boundary():
    assert len(["a"] * settings.phonetic_short_max_units) <= settings.phonetic_short_max_units
    assert len(["a"] * (settings.phonetic_short_max_units + 1)) > settings.phonetic_short_max_units
