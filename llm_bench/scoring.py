"""Punteggio delle risposte del tutor (senza dipendenze, testabile da solo)."""
import re

_IT_WORDS = {"il", "la", "lo", "le", "gli", "di", "che", "non", "si", "per", "un", "una", "è", "con", "in",
             "si", "dopo", "dopo", "invece", "verbo", "va", "usa", "usare", "dire", "deve", "essere"}


def norm(s: str) -> str:
    s = (s or "").lower().replace("’", "'")
    s = re.sub(r"[^\w\s']", " ", s)
    return " ".join(s.split())


def looks_italian(text: str) -> bool:
    words = re.findall(r"\w+", (text or "").lower())
    return sum(w in _IT_WORDS for w in words) >= 2


def speakable(reply: str, max_words: int = 55) -> bool:
    """La risposta verrà letta dal TTS: niente markdown, elenchi o testo troppo lungo."""
    if not reply or len(reply.split()) > max_words:
        return False
    return not re.search(r"[*#`]|^\s*[-•]\s", reply, flags=re.M)


def score_case(case: dict, out: dict) -> dict:
    """out = dict già validato con le chiavi del tutor. Ritorna i flag di successo del caso."""
    if case.get("manual"):
        return {"manual": True, "pass": None, "explanation_it": None,
                "speakable": speakable(out.get("reply", ""))}
    corrected = norm(out.get("corrected_sentence", ""))
    # come nell'app: "corretto" = nessuna correzione mostrata (is_correct=false senza correzioni non conta)
    is_ok = not out.get("corrections")
    expl = [c.get("explanation_it", "") for c in out.get("corrections", []) if isinstance(c, dict)]
    res = {"explanation_it": (all(looks_italian(e) for e in expl) if expl else None),
           "speakable": speakable(out.get("reply", ""))}
    if case.get("asr_noise"):
        # trascrizione sbagliata di Whisper: non va corretta come grammatica né deve deviare la conversazione
        forbidden = [norm(f) for f in case.get("forbidden_originals", [])]
        chased = [c for c in out.get("corrections", []) if isinstance(c, dict)
                  and any(f in norm(c.get("original", "")) for f in forbidden)]
        derailed = any(norm(w) in norm(out.get("reply", "")) for w in case.get("reply_must_not", []))
        res["false_positive"] = bool(chased) or not is_ok
        res["pass"] = not res["false_positive"] and not derailed
        return res
    if case["error"]:
        # più controlli indipendenti (frasi con più errori): ognuno deve passare
        checks = case.get("checks") or [{"have_any": case.get("must_have_any", []), "not": case.get("must_not", [])}]
        all_ok = all(any(norm(h) in corrected for h in ch.get("have_any", []))
                     and not any(norm(m) in corrected for m in ch.get("not", [])) for ch in checks)
        res["detected"] = (not is_ok) or corrected != norm(case["text"])
        res["pass"] = (not is_ok) and all_ok
    else:
        res["false_positive"] = not is_ok
        res["pass"] = not res["false_positive"]
    return res
