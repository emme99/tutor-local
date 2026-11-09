"""phonetic_tips.py — suggerimenti fonetici deterministici per parlanti italiani.

Nessuna chiamata LLM, nessuna dipendenza da torch/transformers.
Ogni regola è espressa come una funzione di matching sulle operazioni di
allineamento restituite da phonetics.align().

Formato di ogni issue restituita:
    {
        "word":     str,   # parola attesa coinvolta
        "expected": str,   # simbolo/sequenza attesa
        "heard":    str,   # simbolo/sequenza percepita (o "")
        "tip_it":   str,   # suggerimento in italiano (tono cauto)
        "severity": str,   # "high" | "medium" | "low"
    }
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Tabella dei pattern — una riga per regola.
# Ogni entry: (name, match_fn, tip_it, severity)
# match_fn riceve (op, exp, heard) e restituisce True/False.
# ---------------------------------------------------------------------------

_PATTERN_TABLE: list[tuple[str, object, str, str]] = []


def _pat(name: str, severity: str, tip: str):
    """Decoratore-factory per registrare una funzione di pattern."""
    def _register(fn):
        _PATTERN_TABLE.append((name, fn, tip, severity))
        return fn
    return _register


# --- consonanti difficili per italiani ---

@_pat(
    "th_voiceless",
    severity="high",
    tip=(
        "Suono /θ/ (th sordo, es. 'think'): sembra che tu stia dicendo /t/, /s/ o /f/. "
        "Metti la punta della lingua tra i denti e soffia senza far vibrare la gola."
    ),
)
def _th_voiceless(op: str, exp: str | None, heard: str | None) -> bool:
    return op == "sub" and exp == "θ" and heard in {"t", "s", "f", "d", "ts", "dz"}


@_pat(
    "th_voiced",
    severity="high",
    tip=(
        "Suono /ð/ (th sonoro, es. 'this'): sembra che tu stia dicendo /d/ o /z/. "
        "Lingua tra i denti con vibrazione della gola."
    ),
)
def _th_voiced(op: str, exp: str | None, heard: str | None) -> bool:
    return op == "sub" and exp == "ð" and heard in {"d", "z", "v", "dz"}


@_pat(
    "h_deletion",
    severity="high",
    tip=(
        "La /h/ non si sente: sembra che tu la stia omettendo. "
        "Soffia leggermente all'inizio della sillaba (come un respiro aspirato)."
    ),
)
def _h_deletion(op: str, exp: str | None, heard: str | None) -> bool:
    return op == "del" and exp == "h"


@_pat(
    "ng_plus_g",
    severity="medium",
    tip=(
        "Suono /ŋ/ (es. 'running', 'singing'): sembra che tu aggiunga una /g/ dopo. "
        "In inglese il /ŋ/ è finale: non si sente la /g/ separata."
    ),
)
def _ng_plus_g(op: str, exp: str | None, heard: str | None) -> bool:
    # Sostituisce ŋ con ŋg (tokenizzato come due unità: ins di 'g' dopo ŋ)
    return op == "sub" and exp == "ŋ" and heard in {"ŋɡ", "ŋg", "ng"}


@_pat(
    "sibilant_confusion",
    severity="medium",
    tip=(
        "Attenzione a /ʃ/ (sh), /tʃ/ (ch), /dʒ/ (j) e /ʒ/ (vision): "
        "sembra che tu stia confondendo questi suoni. Sono quattro suoni distinti."
    ),
)
def _sibilant_confusion(op: str, exp: str | None, heard: str | None) -> bool:
    sibilants = {"ʃ", "tʃ", "dʒ", "ʒ", "s", "z"}
    return (
        op == "sub"
        and exp in sibilants
        and heard in sibilants
        and exp != heard
        and not (exp in {"s", "z"} and heard in {"s", "z"})  # s↔z è low, non sibilant
    )


@_pat(
    "final_consonant_deleted",
    severity="high",
    tip=(
        "Consonante finale omessa: sembra che tu non stia pronunciando il suono finale "
        "della parola. L'inglese richiede di chiudere la consonante finale chiaramente."
    ),
)
def _final_consonant_deleted(op: str, exp: str | None, heard: str | None) -> bool:
    # Rilevato dal chiamante come ultima operazione di una parola che è una delezione
    # di una consonante — viene impostato context="word_final_del" da get_issues
    return False  # gestito in get_issues con contesto


@_pat(
    "ed_suffix_deleted",
    severity="high",
    tip=(
        "Il suffisso -ed non si sente: sembra che tu lo stia omettendo. "
        "Va pronunciato /t/ (walked), /d/ (played) o /ɪd/ (wanted) a seconda del contesto."
    ),
)
def _ed_suffix_deleted(op: str, exp: str | None, heard: str | None) -> bool:
    # Delezione di t/d/ɪd a fine parola — gestito con contesto in get_issues
    return False  # gestito in get_issues con contesto


@_pat(
    "prevovel_s_insertion",
    severity="medium",
    tip=(
        "Vocale iniziale aggiunta prima di s+consonante: sembra che tu dica /ɪ/ o /e/ "
        "prima della parola (es. 'istreet' invece di 'street'). "
        "In inglese le parole cominciano direttamente con la consonante."
    ),
)
def _prevowel_s_insertion(op: str, exp: str | None, heard: str | None) -> bool:
    # Inserzione di una vocale (ɪ/e/ɛ/a) PRIMA della parola — gestito con contesto
    return False  # gestito in get_issues con contesto


@_pat(
    "final_vowel_insertion",
    severity="medium",
    tip=(
        "Vocale aggiunta dopo la consonante finale: sembra che tu stia aggiungendo "
        "una vocale alla fine della parola (es. 'doga' invece di 'dog'). "
        "Chiudi la consonante senza aggiungere suono."
    ),
)
def _final_vowel_insertion(op: str, exp: str | None, heard: str | None) -> bool:
    # Inserzione di vocale DOPO l'ultima unità attesa — gestito con contesto
    return False  # gestito in get_issues con contesto


# --- vocali difficili ---

@_pat(
    "short_i",
    severity="medium",
    tip=(
        "Vocale breve /ɪ/ (es. 'ship'): sembra che tu la stia pronunciando come "
        "una /iː/ lunga (es. 'sheep'). La /ɪ/ è più corta, rilassata e centrale."
    ),
)
def _short_i(op: str, exp: str | None, heard: str | None) -> bool:
    return op == "sub" and exp == "ɪ" and heard in {"iː", "i"}


@_pat(
    "short_u",
    severity="medium",
    tip=(
        "Vocale breve /ʊ/ (es. 'pull'): sembra che tu la stia pronunciando come "
        "una /uː/ lunga (es. 'pool'). La /ʊ/ è più breve e meno arrotondata."
    ),
)
def _short_u(op: str, exp: str | None, heard: str | None) -> bool:
    return op == "sub" and exp == "ʊ" and heard in {"uː", "u"}


@_pat(
    "schwa_substituted",
    severity="low",
    tip=(
        "La vocale ridotta /ə/ (schwa, es. 'about', 'sofa') sembra sostituita "
        "con una vocale piena. Lo schwa è breve e neutro, come un suono indistinto."
    ),
)
def _schwa(op: str, exp: str | None, heard: str | None) -> bool:
    vowels = {"a", "e", "i", "o", "u", "æ", "ɛ", "ɔ", "ʌ"}
    return op == "sub" and exp == "ə" and heard in vowels


@_pat(
    "ae_substituted",
    severity="medium",
    tip=(
        "Vocale /æ/ (es. 'cat', 'back'): sembra che tu stia dicendo /a/ o /ɛ/. "
        "La /æ/ è la 'a' inglese aperta, più avanzata della 'a' italiana."
    ),
)
def _ae_sub(op: str, exp: str | None, heard: str | None) -> bool:
    return op == "sub" and exp == "æ" and heard in {"a", "ɛ", "e", "ə"}


@_pat(
    "wedge_substituted",
    severity="medium",
    tip=(
        "Vocale /ʌ/ (es. 'cup', 'love'): sembra che tu stia dicendo /a/ o /o/. "
        "La /ʌ/ è una vocale centrale medio-aperta, non è né /a/ né /o/ italiana."
    ),
)
def _wedge_sub(op: str, exp: str | None, heard: str | None) -> bool:
    return op == "sub" and exp == "ʌ" and heard in {"a", "o", "ɔ", "ə"}


# ---------------------------------------------------------------------------
# Regole contestuali (gestite direttamente in get_issues, non via _PATTERN_TABLE)
# ---------------------------------------------------------------------------

_VOWELS = frozenset("aeiouæɛɪʊɔʌəɑɐɨʏøœ")
_VOWELS_IPA = frozenset({
    "a", "e", "i", "o", "u",
    "æ", "ɛ", "ɪ", "ʊ", "ɔ", "ʌ", "ə", "ɑ", "ɐ", "ɨ",
    "eɪ", "aɪ", "oʊ", "aʊ", "ɔɪ",  # diphthongs
})


def _is_vowel_unit(unit: str) -> bool:
    return unit in _VOWELS_IPA or (len(unit) == 1 and unit in _VOWELS)


def _is_consonant_unit(unit: str) -> bool:
    return not _is_vowel_unit(unit)


# ---------------------------------------------------------------------------
# Funzione principale
# ---------------------------------------------------------------------------

def get_issues(
    ops: list[dict],
    word_data: list[dict],
    unit_to_word: list[int],
    lenient: bool = True,
    max_issues: int = 2,
) -> list[dict]:
    """Analizza le operazioni di allineamento e restituisce al massimo *max_issues* problemi.

    Args:
        ops: lista di operazioni da phonetics.align() (con expected_idx, predicted_idx, cost…).
        word_data: lista di {"word": str, "units": list[str]} da _text_ipa_words().
        unit_to_word: mappa indice_simbolo → indice_parola.
        lenient: se True, salta i problemi di qualità vocalica pura (severity="low").
        max_issues: numero massimo di issue da restituire (default 2).

    Returns:
        Lista di dict con chiavi: word, expected, heard, tip_it, severity.
    """
    if not ops or not word_data:
        return []

    _SEV_RANK = {"high": 0, "medium": 1, "low": 2}
    issues: list[dict] = []
    seen_names: set[str] = set()  # una regola per tipo, non spam

    # Costruiamo indice parola → suoi ops in ordine
    word_ops: list[list[dict]] = [[] for _ in word_data]
    for op in ops:
        exp_idx = op.get("expected_idx")
        if exp_idx is not None and exp_idx < len(unit_to_word):
            w_idx = unit_to_word[exp_idx]
            word_ops[w_idx].append(op)

    # Raccogliamo le "trailing insertions" per ogni parola: ops con exp_idx=None
    # che compaiono immediatamente DOPO l'ultima op attribuita alla parola
    # (utile per vocale finale inserita, es. "doga" → "dog").
    last_word_expected_idx: list[int] = []
    for wd_local in word_data:
        last_word_expected_idx.append(-1)
    cur_w = 0
    for op in ops:
        exp_idx = op.get("expected_idx")
        if exp_idx is not None and exp_idx < len(unit_to_word):
            cur_w = unit_to_word[exp_idx]
            last_word_expected_idx[cur_w] = exp_idx

    # Scorriamo ops per trovare inserzioni trailing per l'ultima parola
    # (inserzioni dopo tutte le expected_idx della parola)
    if word_data:
        last_w = len(word_data) - 1
        last_expected_of_word = last_word_expected_idx[last_w]
        trailing_ins: list[dict] = []
        past_last = False
        for op in ops:
            exp_idx = op.get("expected_idx")
            if exp_idx is not None and exp_idx == last_expected_of_word:
                past_last = True
                continue
            if past_last and op["op"] == "ins":
                trailing_ins.append(op)
            elif past_last and exp_idx is not None:
                break
        # Aggiungi le trailing_ins alla parola finale
        word_ops[last_w].extend(trailing_ins)

    def _word_of(op: dict) -> str:
        exp_idx = op.get("expected_idx")
        if exp_idx is not None and exp_idx < len(unit_to_word):
            return word_data[unit_to_word[exp_idx]]["word"]
        return ""

    def _add(name: str, word: str, exp: str, heard: str, tip: str, sev: str):
        if name in seen_names:
            return
        if lenient and sev == "low":
            return
        seen_names.add(name)
        issues.append({
            "word": word,
            "expected": exp,
            "heard": heard,
            "tip_it": tip,
            "severity": sev,
        })

    # 1. Regole tabellari (simbolo per simbolo)
    for op in ops:
        o = op["op"]
        exp = op.get("expected")
        heard = op.get("heard")
        word = _word_of(op)
        for name, fn, tip, sev in _PATTERN_TABLE:
            if name in seen_names:
                continue
            if fn(o, exp, heard):
                _add(name, word, exp or "", heard or "", tip, sev)

    # 2. Regola contestuale: vocale pre-parola inserita (es. istreet → street)
    #    Prima op è un'inserzione di vocale, seconda è una consonante
    if len(ops) >= 2:
        first = ops[0]
        if (
            first["op"] == "ins"
            and first.get("heard") is not None
            and _is_vowel_unit(first["heard"])
        ):
            # La parola attesa inizia con consonante o s-cluster
            if word_data and word_data[0]["units"] and _is_consonant_unit(word_data[0]["units"][0]):
                _add(
                    "prevovel_s_insertion",
                    word_data[0]["word"],
                    "",
                    first["heard"],
                    (
                        "Vocale iniziale aggiunta prima della parola: sembra che tu dica "
                        f"/{first['heard']}/ prima di '{word_data[0]['word']}'. "
                        "In inglese non si aggiunge vocale prima delle consonanti iniziali."
                    ),
                    "medium",
                )

    # 3. Regola contestuale per ogni parola: vocale finale inserita / consonante finale eliminata
    for w_idx, (wd, w_ops_list) in enumerate(zip(word_data, word_ops)):
        if not w_ops_list:
            continue
        expected_units = wd["units"]
        if not expected_units:
            continue

        last_expected_unit = expected_units[-1]
        last_op = w_ops_list[-1]

        # 3a. Consonante finale eliminata (non tʃ/dʒ — già coperti da sibilant)
        if (
            last_op["op"] == "del"
            and last_op.get("expected") is not None
            and _is_consonant_unit(last_op["expected"])
            and last_op["expected"] not in {"tʃ", "dʒ", "ŋ"}
        ):
            exp_c = last_op["expected"]
            # Prova a distinguere -ed dalla consonante finale generica
            is_ed = exp_c in {"t", "d"} and len(expected_units) >= 2
            if is_ed:
                _add(
                    "ed_suffix_deleted",
                    wd["word"],
                    exp_c,
                    "",
                    (
                        f"Il suono finale /{exp_c}/ di '{wd['word']}' non si sente: "
                        "sembra che tu lo stia omettendo. Se è un verbo al passato "
                        "(-ed), va pronunciato /t/, /d/ o /ɪd/ secondo il contesto."
                    ),
                    "high",
                )
            else:
                _add(
                    "final_consonant_deleted",
                    wd["word"],
                    exp_c,
                    "",
                    (
                        f"La consonante finale /{exp_c}/ di '{wd['word']}' non si sente: "
                        "sembra che tu la stia omettendo. L'inglese richiede di "
                        "chiudere chiaramente la consonante finale."
                    ),
                    "high",
                )

        # 3b. Vocale finale inserita dopo consonante attesa
        if (
            last_op["op"] == "ins"
            and last_op.get("heard") is not None
            and _is_vowel_unit(last_op["heard"])
            and _is_consonant_unit(last_expected_unit)
        ):
            _add(
                "final_vowel_insertion",
                wd["word"],
                "",
                last_op["heard"],
                (
                    f"Vocale /{last_op['heard']}/ aggiunta dopo '{wd['word']}': "
                    "sembra che tu stia aggiungendo un suono finale. "
                    "Chiudi la consonante senza aggiungere vocale."
                ),
                "medium",
            )

    # Ordina per severità e restituisci al massimo max_issues
    issues.sort(key=lambda x: _SEV_RANK.get(x["severity"], 9))
    return issues[:max_issues]
