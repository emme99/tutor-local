#!/usr/bin/env python3
"""Confronta motori STT/ASR sulle stesse registrazioni e genera un report.

Uso:
  python run_bench.py                         # tutti i motori di config.toml su recordings/mac
  python run_bench.py --engines mio_stt gemma_verbatim
  python run_bench.py --only it_numbers pron01
  python run_bench.py --report-only           # rigenera solo il report
  python run_bench.py --export-template box   # crea manual/box.csv da compilare a mano
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("Serve Python 3.11+ (modulo tomllib).")

import soundfile as sf

ROOT = Path(__file__).parent
AUDIO_EXT = (".wav", ".m4a", ".mp3", ".aac", ".ogg", ".opus", ".flac", ".amr", ".3gp", ".mp4")
LANG_NAMES = {"it": "Italian", "en": "English"}


# ───────────────────────── metriche ─────────────────────────
def normalize(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", s)   # 1.234 -> 1234
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)    # 1,234 -> 1234
    s = re.sub(r"(?<=\d)[,:.](?=\d)", " ", s)        # 17:45, 50,5 -> 17 45
    s = re.sub(r"[^\w\s]", " ", s).replace("_", " ")
    return s.split()


def edit_distance(a, b) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def score_item(it: dict, hyp: str):
    """Restituisce (err_parole, n_parole, err_char, n_char) sulla variante di riferimento migliore."""
    best = None
    for ref in [it["text"]] + it.get("alt", []):
        r, h = normalize(ref), normalize(hyp)
        e = edit_distance(r, h)
        rate = e / len(r) if r else 0
        if best is None or rate < best[0]:
            best = (rate, e, len(r), ref)
    _, e, n, ref = best
    rc, hc = " ".join(normalize(ref)), " ".join(normalize(hyp))
    return e, n, edit_distance(rc, hc), len(rc)


def agg(rows):
    if not rows:
        return None, None
    n, e = sum(r[1] for r in rows), sum(r[0] for r in rows)
    cn, ce = sum(r[3] for r in rows), sum(r[2] for r in rows)
    return (100 * e / n if n else None), (100 * ce / cn if cn else None)


def pct(x):
    return "-" if x is None else f"{x:.1f}%"


# ───────────────────────── audio ─────────────────────────
def prepare(p: Path, cache: Path) -> Path:
    if p.suffix.lower() == ".wav":
        info = sf.info(str(p))
        if info.samplerate == 16000 and info.channels == 1:
            return p
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{p.stem}.wav"
    if not out.exists() or out.stat().st_mtime < p.stat().st_mtime:
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p),
                            "-ac", "1", "-ar", "16000", str(out)], check=True)
        except FileNotFoundError:
            sys.exit("ffmpeg non trovato: brew install ffmpeg")
    return out


def make_resolver(set_name: str):
    src, cache = ROOT / "recordings" / set_name, ROOT / ".cache" / set_name

    def resolve(stem: str):
        for ext in AUDIO_EXT:
            p = src / f"{stem}{ext}"
            if p.exists():
                return prepare(p, cache)
        return None

    return resolve


def duration(p: Path) -> float:
    return float(sf.info(str(p)).duration)


# ───────────────────────── motori ─────────────────────────
class GemmaBase:
    """Prompt condivisi per Gemma; le sottoclassi implementano _ask(path, text)."""
    needs_audio = True

    def __init__(self, name, cfg):
        self.name = name
        self.style = cfg.get("prompt_style", "plain")

    def _ask(self, path: Path, text: str) -> str:
        raise NotImplementedError

    def transcribe(self, path, item):
        L = LANG_NAMES[item["lang"]]
        if self.style == "verbatim":
            q = (f"Transcribe the following speech segment in {L}, word for word, exactly as it is "
                 f"pronounced. Do not correct grammar, vocabulary or pronunciation, and do not "
                 f"replace unclear words with likely ones. Output only the transcription.")
        else:
            q = f"Transcribe the following speech segment in {L} into {L} text."
        return self._ask(path, q)

    def translate(self, path, item):
        src = LANG_NAMES[item["lang"]]
        tgt = LANG_NAMES["it" if item["lang"] == "en" else "en"]
        return self._ask(path, f"Translate the following speech from {src} into {tgt}. "
                               f"Output only the {tgt} translation.")

    def critique(self, path, item):
        L = LANG_NAMES[item["lang"]]
        return self._ask(path, (
            f'A non-native speaker was asked to read this {L} sentence aloud: "{item["text"]}". '
            f"Listen carefully. List only the words that were clearly mispronounced, separated by "
            f"commas. If all words were pronounced acceptably, answer exactly NONE. "
            f"Output only the list or NONE."))


_MLX_CACHE: dict = {}


class GemmaMLX(GemmaBase):
    def __init__(self, name, cfg):
        super().__init__(name, cfg)
        self.model_id = cfg["model"]
        self.max_tokens = cfg.get("max_tokens", 400)

    def _ask(self, path, text):
        from mlx_vlm import generate, load
        from mlx_vlm.prompt_utils import apply_chat_template
        if self.model_id not in _MLX_CACHE:
            _MLX_CACHE[self.model_id] = load(self.model_id)
        model, processor = _MLX_CACHE[self.model_id]
        prompt = apply_chat_template(processor, model.config, text, num_audios=1)
        out = generate(model, processor, prompt, audio=[str(path)],
                       max_tokens=self.max_tokens, verbose=False)
        if isinstance(out, tuple):
            out = out[0]
        return str(getattr(out, "text", out)).strip()


class GemmaOpenAI(GemmaBase):
    """Gemma servito da llama-server / LM Studio con chat completions + input_audio."""

    def __init__(self, name, cfg):
        super().__init__(name, cfg)
        self.url = cfg["base_url"].rstrip("/") + "/chat/completions"
        self.model = cfg.get("model", "gemma-4-e4b-it")
        self.key = cfg.get("api_key", "local")

    def _ask(self, path, text):
        import httpx
        b64 = base64.b64encode(path.read_bytes()).decode()
        payload = {"model": self.model, "temperature": 0, "messages": [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
            {"type": "text", "text": text}]}]}
        r = httpx.post(self.url, json=payload, headers={"Authorization": f"Bearer {self.key}"}, timeout=300)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


class OpenAISTT:
    needs_audio = True

    def __init__(self, name, cfg):
        self.name = name
        self.url = cfg["base_url"].rstrip("/") + "/audio/transcriptions"
        self.model = cfg.get("model", "whisper-1")
        self.key = cfg.get("api_key", "local")
        self.send_language = cfg.get("send_language", True)

    def transcribe(self, path, item):
        import httpx
        data = {"model": self.model, "response_format": "json"}
        if self.send_language:
            data["language"] = item["lang"]
        with open(path, "rb") as f:
            r = httpx.post(self.url, headers={"Authorization": f"Bearer {self.key}"}, data=data,
                           files={"file": (path.name, f, "audio/wav")}, timeout=300)
        r.raise_for_status()
        return r.json()["text"].strip()


class MLXWhisper:
    needs_audio = True

    def __init__(self, name, cfg):
        self.name = name
        self.repo = cfg.get("model", "mlx-community/whisper-large-v3-turbo")
        self.initial_prompt = cfg.get("initial_prompt")

    def transcribe(self, path, item):
        import mlx_whisper
        kw = {"initial_prompt": self.initial_prompt} if self.initial_prompt else {}
        out = mlx_whisper.transcribe(str(path), path_or_hf_repo=self.repo, language=item["lang"],
                                     condition_on_previous_text=False, **kw)
        return out["text"].strip()


class Manual:
    """Risultati inseriti a mano (es. Box su S26). CSV con colonne: id,phrase,text,translation."""
    needs_audio = False

    def __init__(self, name, cfg):
        self.name = name
        p = ROOT / cfg["csv"]
        if not p.exists():
            raise FileNotFoundError(f"{p} non esiste (crealo con --export-template {name})")
        with open(p, newline="", encoding="utf-8") as f:
            self.rows = {r["id"]: r for r in csv.DictReader(f)}

    def transcribe(self, path, item):
        t = (self.rows.get(item["id"], {}).get("text") or "").strip()
        return t or None

    def translate(self, path, item):
        t = (self.rows.get(item["id"], {}).get("translation") or "").strip()
        return t or None


ENGINE_TYPES = {"openai_stt": OpenAISTT, "mlx_whisper": MLXWhisper, "gemma_mlx": GemmaMLX,
                "gemma_openai": GemmaOpenAI, "manual": Manual}


# ───────────────────────── esecuzione ─────────────────────────
def fingerprint(p) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12]


def run_engine(name, eng, items, resolve, res, force):
    """Ri-esegue un risultato se manca, se force, o se l'audio (o la riga manuale) è cambiato."""
    tr = res.setdefault("transcribe", {})
    tl = res.setdefault("translate", {})
    pr = res.setdefault("pron", {})

    def stale(store, iid, h):
        return force or iid not in store or store[iid].get("audio") != h

    def key_for(iid, p):
        if eng.needs_audio:
            return fingerprint(p)
        row = getattr(eng, "rows", {}).get(iid, {})
        return hashlib.sha1(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]

    # warm-up (carica il modello senza contarlo nei tempi)
    if eng.needs_audio:
        for it in items:
            p = resolve(it["id"])
            if p and stale(tr, it["id"], fingerprint(p)):
                try:
                    eng.transcribe(p, it)
                except Exception as e:  # noqa: BLE001
                    print(f"[{name}] warm-up fallito: {e}")
                break

    for it in items:
        iid = it["id"]
        p = resolve(iid)
        if p is None and eng.needs_audio:
            continue
        h = key_for(iid, p)

        if stale(tr, iid, h):
            try:
                t0 = time.perf_counter()
                hyp = eng.transcribe(p, it)
                dt = time.perf_counter() - t0
            except Exception as e:  # noqa: BLE001
                print(f"[{name}] {iid}: ERRORE {e}")
                continue
            if hyp is not None:
                tr[iid] = {"hyp": hyp, "sec": round(dt, 2), "dur": round(duration(p), 2) if p else 0, "audio": h}
                print(f"[{name}] {iid}: {hyp[:70]}")

        if it.get("ref_translation") and hasattr(eng, "translate") and stale(tl, iid, h):
            try:
                out = eng.translate(p, it)
            except Exception as e:  # noqa: BLE001
                print(f"[{name}] {iid} translate: ERRORE {e}")
                out = None
            if out:
                tl[iid] = {"hyp": out, "audio": h}

        if it["category"] == "en_pron" and hasattr(eng, "critique"):
            p_ok = resolve(iid + "_ok")
            if p_ok:
                hh = h + fingerprint(p_ok)
                if stale(pr, iid, hh):
                    try:
                        pr[iid] = {"bad": eng.critique(p, it), "ok": eng.critique(p_ok, it), "audio": hh}
                        print(f"[{name}] {iid} critique: bad={pr[iid]['bad'][:40]!r} ok={pr[iid]['ok'][:40]!r}")
                    except Exception as e:  # noqa: BLE001
                        print(f"[{name}] {iid} critique: ERRORE {e}")


# ───────────────────────── report ─────────────────────────
def build_report(items, all_res, set_name) -> str:
    by_id = {it["id"]: it for it in items}
    engines = list(all_res)
    L = ["# Report benchmark STT/ASR", "",
         f"Set di registrazioni: `{set_name}` · Motori: {', '.join(engines)}", ""]

    scored = {e: {} for e in engines}
    for e in engines:
        for iid, rec in all_res[e].get("transcribe", {}).items():
            it = by_id.get(iid)
            if it and it["category"] != "en_pron":
                scored[e][iid] = score_item(it, rec["hyp"])
    common = set.intersection(*[set(scored[e]) for e in engines]) if engines else set()
    ordered = [it["id"] for it in items if it["id"] in common]
    union = set().union(*[set(scored[e]) for e in engines]) if engines else set()
    missing = [it["id"] for it in items if it["id"] in union - common]

    L += [f"## Riepilogo (su {len(common)} frasi comuni a tutti i motori)", "",
          "| Motore | WER it | WER en | CER | RTF mediano |", "|---|---|---|---|---|"]
    for e in engines:
        rows = {i: scored[e][i] for i in ordered}
        wit = agg([v for i, v in rows.items() if by_id[i]["lang"] == "it"])[0]
        wen = agg([v for i, v in rows.items() if by_id[i]["lang"] == "en"])[0]
        cer = agg(list(rows.values()))[1]
        rtfs = [r["sec"] / r["dur"] for r in all_res[e].get("transcribe", {}).values() if r["dur"] and r["sec"] > 0]
        rtf = f"{statistics.median(rtfs):.2f}" if rtfs else "-"
        L.append(f"| {e} | {pct(wit)} | {pct(wen)} | {pct(cer)} | {rtf} |")
    if missing:
        L += ["", f"_Escluse perché mancanti in almeno un motore: {', '.join(missing)}_"]
    L += ["", "_WER/CER più bassi sono meglio. RTF = tempo di calcolo / durata audio (<1 = più veloce del parlato). "
          "Le frasi `en_pron` sono escluse: hanno una sezione dedicata._", ""]

    cats = []
    for it in items:
        if it["category"] != "en_pron" and it["category"] not in cats:
            cats.append(it["category"])
    L += ["## WER per categoria", "", "| Categoria | " + " | ".join(engines) + " |",
          "|---|" + "---|" * len(engines)]
    for c in cats:
        ids = [i for i in ordered if by_id[i]["category"] == c]
        if not ids:
            continue
        cells = [pct(agg([scored[e][i] for i in ids])[0]) for e in engines]
        L.append(f"| {c} | " + " | ".join(cells) + " |")
    L.append("")

    L += ["## Dettaglio errori", ""]
    for iid in ordered:
        it = by_id[iid]
        if all(scored[e][iid][0] == 0 for e in engines):
            continue
        dur = next((all_res[e]["transcribe"][iid]["dur"] for e in engines
                    if all_res[e]["transcribe"].get(iid, {}).get("dur")), 0)
        L += [f"**{iid}** · {it['category']} · {dur:.1f} s  ", f"Riferimento: {it['text']}"]
        for e in engines:
            v = scored[e][iid]
            L.append(f"- `{e}` ({pct(100 * v[0] / v[1] if v[1] else 0)}): {all_res[e]['transcribe'][iid]['hyp']}")
        L.append("")

    long_ids = [i for i in ordered
                if any(all_res[e]["transcribe"].get(i, {}).get("dur", 0) >= 25 for e in engines)]
    if long_ids:
        L += ["## Clip lunghe (limite audio di Gemma: 30 s)", "",
              "| Frase | Durata | Motore | WER | Parole output/riferimento |", "|---|---|---|---|---|"]
        for i in long_ids:
            dur = max(all_res[e]["transcribe"].get(i, {}).get("dur", 0) for e in engines)
            for e in engines:
                v = scored[e][i]
                ratio = len(normalize(all_res[e]["transcribe"][i]["hyp"])) / max(v[1], 1)
                L.append(f"| {i} | {dur:.1f} s | {e} | {pct(100 * v[0] / v[1] if v[1] else 0)} | {ratio:.0%} |")
        L += ["", "_Un rapporto molto sotto il 100% su clip >30 s indica troncamento._", ""]

    pitems = [it for it in items if it["category"] == "en_pron"]
    has_pron = any(all_res[e].get("transcribe", {}).get(it["id"]) for e in engines for it in pitems)
    if has_pron:
        L += ["## Test pronuncia", "",
              "### A) L'ASR riporta ciò che hai detto o lo corregge?", "",
              "Sulla take *sbagliata di proposito*: **fedele** = scrive la parola pronunciata (es. «sheep»); "
              "**normalizzato** = scrive la parola attesa (es. «ship»).", "",
              "| Motore | Fedele | Normalizzato | Altro |", "|---|---|---|---|"]
        for e in engines:
            cnt = {"fedele": 0, "normalizzato": 0, "altro": 0}
            for it in pitems:
                rec = all_res[e].get("transcribe", {}).get(it["id"])
                if not rec:
                    continue
                toks = normalize(rec["hyp"])
                bad, good = normalize(it["bad_say"])[0] in toks, normalize(it["focus"])[0] in toks
                cnt["fedele" if bad and not good else "normalizzato" if good and not bad else "altro"] += 1
            L.append(f"| {e} | {cnt['fedele']} | {cnt['normalizzato']} | {cnt['altro']} |")
        L.append("")

        rows = []
        for e in engines:
            pr = all_res[e].get("pron", {})
            if not pr:
                continue
            hit = fa = disc = 0
            for iid, r in pr.items():
                it = by_id[iid]
                tb, to = normalize(r["bad"]), normalize(r["ok"])
                h_ = tb[:1] != ["none"] and (normalize(it["focus"])[0] in tb or normalize(it["bad_say"])[0] in tb)
                f_ = to[:1] != ["none"]
                hit += h_
                fa += f_
                disc += h_ and not f_
            rows.append(f"| {e} | {hit}/{len(pr)} | {fa}/{len(pr)} | {disc}/{len(pr)} |")
        if rows:
            L += ["### B) Domanda diretta al modello («quali parole sono pronunciate male?»)", "",
                  "| Motore | Rilevato (take sbagliata) | Falsi allarmi (take corretta) | Discrimina (rilevato E nessun falso allarme) |",
                  "|---|---|---|---|"]
            L += rows + ["",
                         "_Conta soprattutto l'ultima colonna: un valutatore utile segnala l'errore sulla take sbagliata "
                         "e risponde NONE su quella corretta._", ""]
            for e in engines:
                for iid, r in all_res[e].get("pron", {}).items():
                    L.append(f"- `{e}` {iid} (parola «{by_id[iid]['focus']}»): sbagliata → {r['bad']!r} · corretta → {r['ok']!r}")
            L.append("")

    tl_ids = [it["id"] for it in items if any(it["id"] in all_res[e].get("translate", {}) for e in engines)]
    if tl_ids:
        L += ["## Traduzione parlato → testo (non punteggiata, da leggere)", ""]
        for iid in tl_ids:
            L += [f"**{iid}** · {by_id[iid]['text']}  ", f"Riferimento: {by_id[iid]['ref_translation']}"]
            for e in engines:
                t = all_res[e].get("translate", {}).get(iid)
                if t:
                    L.append(f"- `{e}`: {t['hyp']}")
            L.append("")
    return "\n".join(L) + "\n"


# ───────────────────────── main ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="mac")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--engines", nargs="*")
    ap.add_argument("--only", nargs="*", help="id, categorie o lingue")
    ap.add_argument("--force", action="store_true", help="ripeti anche i risultati già salvati")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--export-template", metavar="NOME")
    args = ap.parse_args()

    items = json.loads((ROOT / "phrases.json").read_text(encoding="utf-8"))["phrases"]
    if args.only:
        sel = set(args.only)
        items = [i for i in items if i["id"] in sel or i["category"] in sel or i["lang"] in sel]

    if args.export_template:
        out = ROOT / "manual" / f"{args.export_template}.csv"
        out.parent.mkdir(exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "phrase", "text", "translation"])
            for it in items:
                w.writerow([it["id"], it["text"], "", ""])
        print(f"Creato {out}. Compila 'text' (trascrizione data dal motore) e, per le frasi con "
              f"traduzione, 'translation'.")
        return

    cfg = tomllib.loads((ROOT / args.config).read_text(encoding="utf-8"))["engines"]
    names = args.engines or list(cfg)
    res_dir = ROOT / "results" / args.set
    res_dir.mkdir(parents=True, exist_ok=True)
    resolve = make_resolver(args.set)

    all_res = {}
    for name in names:
        rpath = res_dir / f"{name}.json"
        res = json.loads(rpath.read_text(encoding="utf-8")) if rpath.exists() else {}
        if not args.report_only:
            try:
                eng = ENGINE_TYPES[cfg[name]["type"]](name, cfg[name])
            except Exception as e:  # noqa: BLE001
                print(f"[{name}] non avviabile: {e}")
                eng = None
            if eng:
                run_engine(name, eng, items, resolve, res, args.force)
                rpath.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        if res.get("transcribe"):
            all_res[name] = res

    if not all_res:
        sys.exit("Nessun risultato disponibile.")
    report = build_report(json.loads((ROOT / "phrases.json").read_text(encoding="utf-8"))["phrases"],
                          all_res, args.set)
    out = res_dir / "report.md"
    out.write_text(report, encoding="utf-8")
    print(f"\nReport: {out}")


if __name__ == "__main__":
    main()
