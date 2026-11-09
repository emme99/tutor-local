"""Test per phonetic_tips.get_issues().

Nessuna dipendenza da torch/transformers/phonemizer: tutto offline.
"""

from app.phonetic_tips import get_issues

# ---------------------------------------------------------------------------
# Helper: costruisce una singola operazione di allineamento
# ---------------------------------------------------------------------------

def _op(op: str, exp: str | None = None, heard: str | None = None,
        exp_idx: int | None = None, pred_idx: int | None = None,
        cost: float = 1.0) -> dict:
    return {
        "op": op,
        "expected": exp,
        "heard": heard,
        "expected_idx": exp_idx,
        "predicted_idx": pred_idx,
        "cost": cost,
    }


def _word(word: str, units: list[str]) -> dict:
    return {"word": word, "units": units}


def _unit_to_word(word_data: list[dict]) -> list[int]:
    u2w: list[int] = []
    for w_idx, wd in enumerate(word_data):
        for _ in wd["units"]:
            u2w.append(w_idx)
    return u2w


# ---------------------------------------------------------------------------
# Test: lista vuota
# ---------------------------------------------------------------------------

def test_empty_ops_returns_empty():
    assert get_issues([], [], []) == []


def test_empty_word_data_returns_empty():
    ops = [_op("match", "h", "h", exp_idx=0, pred_idx=0, cost=0)]
    assert get_issues(ops, [], []) == []


# ---------------------------------------------------------------------------
# Test: /θ/ → /t/ (th sordo)
# ---------------------------------------------------------------------------

def test_th_voiceless_t():
    # "think" → pronunciato "tink": θ→t
    wd = [_word("think", ["θ", "ɪ", "ŋ", "k"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("sub", "θ", "t", exp_idx=0, pred_idx=0, cost=1.0),
        _op("sub", "ɪ", "ɪ", exp_idx=1, pred_idx=1, cost=0),
        _op("match", "ŋ", "ŋ", exp_idx=2, pred_idx=2, cost=0),
        _op("match", "k", "k", exp_idx=3, pred_idx=3, cost=0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert len(issues) >= 1
    assert issues[0]["severity"] == "high"
    assert "θ" in issues[0]["tip_it"] or "th" in issues[0]["tip_it"]


def test_th_voiceless_s():
    wd = [_word("think", ["θ", "ɪ", "ŋ", "k"])]
    u2w = _unit_to_word(wd)
    ops = [_op("sub", "θ", "s", exp_idx=0, pred_idx=0, cost=1.0)]
    issues = get_issues(ops, wd, u2w)
    assert any(i["severity"] == "high" for i in issues)


# ---------------------------------------------------------------------------
# Test: /ð/ → /d/ (th sonoro)
# ---------------------------------------------------------------------------

def test_th_voiced_d():
    wd = [_word("this", ["ð", "ɪ", "s"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("sub", "ð", "d", exp_idx=0, pred_idx=0, cost=1.0),
        _op("match", "ɪ", "ɪ", exp_idx=1, pred_idx=1, cost=0),
        _op("match", "s", "s", exp_idx=2, pred_idx=2, cost=0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert len(issues) >= 1
    assert issues[0]["severity"] == "high"
    assert "ð" in issues[0]["tip_it"] or "th" in issues[0]["tip_it"]


# ---------------------------------------------------------------------------
# Test: /h/ eliminata
# ---------------------------------------------------------------------------

def test_h_deletion():
    wd = [_word("hello", ["h", "ɛ", "l", "oʊ"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("del", "h", None, exp_idx=0, cost=1.0),
        _op("match", "ɛ", "ɛ", exp_idx=1, pred_idx=0, cost=0),
        _op("match", "l", "l", exp_idx=2, pred_idx=1, cost=0),
        _op("match", "oʊ", "oʊ", exp_idx=3, pred_idx=2, cost=0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert any(i["severity"] == "high" and "/h/" in i["tip_it"] for i in issues)


# ---------------------------------------------------------------------------
# Test: /ɪ/ → /iː/ (ship vs sheep)
# ---------------------------------------------------------------------------

def test_short_i_replaced_by_long():
    wd = [_word("ship", ["ʃ", "ɪ", "p"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("match", "ʃ", "ʃ", exp_idx=0, pred_idx=0, cost=0),
        _op("sub", "ɪ", "iː", exp_idx=1, pred_idx=1, cost=0.5),
        _op("match", "p", "p", exp_idx=2, pred_idx=2, cost=0),
    ]
    issues = get_issues(ops, wd, u2w, lenient=False)
    assert any("ɪ" in i["tip_it"] or "ship" in i["tip_it"].lower() for i in issues)


# ---------------------------------------------------------------------------
# Test: /ʊ/ → /uː/ (pull vs pool)
# ---------------------------------------------------------------------------

def test_short_u_replaced_by_long():
    wd = [_word("pull", ["p", "ʊ", "l"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("match", "p", "p", exp_idx=0, pred_idx=0, cost=0),
        _op("sub", "ʊ", "uː", exp_idx=1, pred_idx=1, cost=0.5),
        _op("match", "l", "l", exp_idx=2, pred_idx=2, cost=0),
    ]
    issues = get_issues(ops, wd, u2w, lenient=False)
    assert any("ʊ" in i["tip_it"] for i in issues)


# ---------------------------------------------------------------------------
# Test: vocale SOLO diff → NO issue in lenient mode
# ---------------------------------------------------------------------------

def test_vowel_only_diff_no_issue_in_lenient():
    # /ɪ/ → /iː/: solo differenza vocalica (severity medium) — in lenient=True deve NON apparire
    # (lenient salta solo severity="low"; medium rimane, quindi testiamo severity=low: schwa)
    wd = [_word("about", ["ə", "b", "aʊ", "t"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("sub", "ə", "a", exp_idx=0, pred_idx=0, cost=0.5),  # schwa→a: low
        _op("match", "b", "b", exp_idx=1, pred_idx=1, cost=0),
        _op("match", "aʊ", "aʊ", exp_idx=2, pred_idx=2, cost=0),
        _op("match", "t", "t", exp_idx=3, pred_idx=3, cost=0),
    ]
    issues_lenient = get_issues(ops, wd, u2w, lenient=True)
    issues_strict = get_issues(ops, wd, u2w, lenient=False)
    # In lenient mode: low severity skipped
    assert all(i["severity"] != "low" for i in issues_lenient)
    # In strict mode: schwa issue should appear
    assert any("ə" in i["tip_it"] for i in issues_strict)


# ---------------------------------------------------------------------------
# Test: vocale pre-parola inserita (istreet → street)
# ---------------------------------------------------------------------------

def test_prevowel_insertion_before_consonant():
    wd = [_word("street", ["s", "t", "r", "iː", "t"])]
    u2w = _unit_to_word(wd)
    # Il riconoscitore ha sentito "istreet": ins ɪ, poi match del resto
    ops = [
        _op("ins", None, "ɪ", exp_idx=None, pred_idx=0, cost=1.0),
        _op("match", "s", "s", exp_idx=0, pred_idx=1, cost=0),
        _op("match", "t", "t", exp_idx=1, pred_idx=2, cost=0),
        _op("match", "r", "r", exp_idx=2, pred_idx=3, cost=0),
        _op("match", "iː", "iː", exp_idx=3, pred_idx=4, cost=0),
        _op("match", "t", "t", exp_idx=4, pred_idx=5, cost=0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert any("vocale" in i["tip_it"].lower() or "street" in i["tip_it"].lower() for i in issues)


# ---------------------------------------------------------------------------
# Test: consonante finale eliminata
# ---------------------------------------------------------------------------

def test_final_consonant_deleted():
    wd = [_word("dog", ["d", "ɒ", "ɡ"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("match", "d", "d", exp_idx=0, pred_idx=0, cost=0),
        _op("match", "ɒ", "ɒ", exp_idx=1, pred_idx=1, cost=0),
        _op("del", "ɡ", None, exp_idx=2, cost=1.0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert any(i["severity"] == "high" for i in issues)
    assert any("dog" in i["word"] or "ɡ" in i["expected"] for i in issues)


# ---------------------------------------------------------------------------
# Test: vocale finale inserita (doga → dog)
# ---------------------------------------------------------------------------

def test_final_vowel_insertion():
    wd = [_word("dog", ["d", "ɒ", "ɡ"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("match", "d", "d", exp_idx=0, pred_idx=0, cost=0),
        _op("match", "ɒ", "ɒ", exp_idx=1, pred_idx=1, cost=0),
        _op("match", "ɡ", "ɡ", exp_idx=2, pred_idx=2, cost=0),
        _op("ins", None, "ə", exp_idx=None, pred_idx=3, cost=1.0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert any("vocale" in i["tip_it"].lower() or "ə" in i["heard"] for i in issues)


# ---------------------------------------------------------------------------
# Test: al massimo max_issues issue restituite
# ---------------------------------------------------------------------------

def test_max_issues_limit():
    # Molti errori contemporanei: θ→t, ð→d, h eliminata, ɪ→iː — deve tornarne max 2
    wd = [
        _word("think", ["θ", "ɪ", "ŋ", "k"]),
        _word("this", ["ð", "ɪ", "s"]),
        _word("hello", ["h", "ɛ", "l", "oʊ"]),
    ]
    u2w = _unit_to_word(wd)
    ops = [
        _op("sub", "θ", "t", exp_idx=0, pred_idx=0, cost=1.0),
        _op("sub", "ɪ", "iː", exp_idx=1, pred_idx=1, cost=0.5),
        _op("match", "ŋ", "ŋ", exp_idx=2, pred_idx=2, cost=0),
        _op("match", "k", "k", exp_idx=3, pred_idx=3, cost=0),
        _op("sub", "ð", "d", exp_idx=4, pred_idx=4, cost=1.0),
        _op("match", "ɪ", "ɪ", exp_idx=5, pred_idx=5, cost=0),
        _op("match", "s", "s", exp_idx=6, pred_idx=6, cost=0),
        _op("del", "h", None, exp_idx=7, cost=1.0),
        _op("match", "ɛ", "ɛ", exp_idx=8, pred_idx=7, cost=0),
        _op("match", "l", "l", exp_idx=9, pred_idx=8, cost=0),
        _op("match", "oʊ", "oʊ", exp_idx=10, pred_idx=9, cost=0),
    ]
    issues = get_issues(ops, wd, u2w, max_issues=2)
    assert len(issues) <= 2


# ---------------------------------------------------------------------------
# Test: nessun errore → nessuna issue
# ---------------------------------------------------------------------------

def test_all_match_no_issues():
    wd = [_word("cat", ["k", "æ", "t"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("match", "k", "k", exp_idx=0, pred_idx=0, cost=0),
        _op("match", "æ", "æ", exp_idx=1, pred_idx=1, cost=0),
        _op("match", "t", "t", exp_idx=2, pred_idx=2, cost=0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert issues == []


# ---------------------------------------------------------------------------
# Test: /æ/ → /a/
# ---------------------------------------------------------------------------

def test_ae_substituted():
    wd = [_word("cat", ["k", "æ", "t"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("match", "k", "k", exp_idx=0, pred_idx=0, cost=0),
        _op("sub", "æ", "a", exp_idx=1, pred_idx=1, cost=0.5),
        _op("match", "t", "t", exp_idx=2, pred_idx=2, cost=0),
    ]
    issues = get_issues(ops, wd, u2w, lenient=False)
    assert any("æ" in i["tip_it"] for i in issues)


# ---------------------------------------------------------------------------
# Test: /ʌ/ → /a/ (cup)
# ---------------------------------------------------------------------------

def test_wedge_substituted():
    wd = [_word("cup", ["k", "ʌ", "p"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("match", "k", "k", exp_idx=0, pred_idx=0, cost=0),
        _op("sub", "ʌ", "a", exp_idx=1, pred_idx=1, cost=0.5),
        _op("match", "p", "p", exp_idx=2, pred_idx=2, cost=0),
    ]
    issues = get_issues(ops, wd, u2w, lenient=False)
    assert any("ʌ" in i["tip_it"] for i in issues)


# ---------------------------------------------------------------------------
# Test: sibilant confusion /ʃ/ → /s/
# ---------------------------------------------------------------------------

def test_sibilant_confusion_sh_s():
    wd = [_word("shoe", ["ʃ", "uː"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("sub", "ʃ", "s", exp_idx=0, pred_idx=0, cost=1.0),
        _op("match", "uː", "uː", exp_idx=1, pred_idx=1, cost=0),
    ]
    issues = get_issues(ops, wd, u2w)
    assert any("ʃ" in i["tip_it"] or "sh" in i["tip_it"] for i in issues)


# ---------------------------------------------------------------------------
# Test: severità high prima di medium
# ---------------------------------------------------------------------------

def test_high_severity_sorted_first():
    # θ→t (high) e ɪ→iː (medium): high deve venire prima
    wd = [_word("think", ["θ", "ɪ", "ŋ", "k"])]
    u2w = _unit_to_word(wd)
    ops = [
        _op("sub", "θ", "t", exp_idx=0, pred_idx=0, cost=1.0),
        _op("sub", "ɪ", "iː", exp_idx=1, pred_idx=1, cost=0.5),
        _op("match", "ŋ", "ŋ", exp_idx=2, pred_idx=2, cost=0),
        _op("match", "k", "k", exp_idx=3, pred_idx=3, cost=0),
    ]
    issues = get_issues(ops, wd, u2w, lenient=False, max_issues=2)
    assert len(issues) >= 1
    assert issues[0]["severity"] == "high"
