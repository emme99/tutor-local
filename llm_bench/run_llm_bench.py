#!/usr/bin/env python3
"""Confronta LLM sul compito del tutor (correzione di frasi di un italiano che parla inglese).

Uso (dalla cartella llm_bench, con il venv del backend attivo):
  python run_llm_bench.py                       # tutti i modelli di models.toml
  python run_llm_bench.py --models gemma4_26b_a4b qwen36_27b
  python run_llm_bench.py --force               # ignora i risultati salvati
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app import modes  # noqa: E402
from app.jsonparse import NotJSON, extract_json  # noqa: E402
from app.providers.llm import chat  # noqa: E402
from app.schemas import TutorOutput  # noqa: E402
from scoring import score_case  # noqa: E402

SYSTEM = modes.system_prompt("conversation", "B1", "en")
BENCH_VERSION = "v2"  # cambia se cambia la logica: invalida i risultati salvati


def effective(cfg: dict) -> dict:
    """Parametri realmente inviati (incluso il default 'thinking spento'): servono anche per la chiave di cache."""
    return {**cfg, "extra_body": cfg.get("extra_body", {"reasoning_effort": "none"}),
            "max_tokens": cfg.get("max_tokens", 900), "json_mode": cfg.get("json_mode", True)}


def key_for(model_cfg: dict, case: dict) -> str:
    blob = json.dumps([BENCH_VERSION, SYSTEM, case["text"], effective(model_cfg)], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


async def run_case(cfg: dict, case: dict) -> dict:
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": case["text"]}]
    eff = effective(cfg)
    t0 = time.perf_counter()
    try:
        text, usage = await chat(msgs, base_url=cfg["base_url"], model=cfg["model"],
                                 json_mode=eff["json_mode"], temperature=0.0,
                                 extra_body=eff["extra_body"], max_tokens=eff["max_tokens"])
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "key": key_for(cfg, case)}
    dt = time.perf_counter() - t0
    rec = {"key": key_for(cfg, case), "sec": round(dt, 2), "raw": text,
           "tokens": usage.get("completion_tokens") or 0, "finish": usage.get("finish_reason"),
           "reasoning_chars": usage.get("reasoning_chars", 0)}
    try:
        out = TutorOutput.model_validate(extract_json(text))
        rec["valid"] = True
        rec["out"] = out.model_dump()
        rec["score"] = score_case(case, rec["out"])
    except (NotJSON, ValueError) as e:
        rec["valid"] = False
        rec["parse_error"] = str(e)[:200]
        if rec["finish"] == "length":
            rec["parse_error"] = "TRONCATO da max_tokens (probabile thinking attivo)"
    return rec


async def run_model(name: str, cfg: dict, cases: list[dict], res: dict, force: bool):
    cs = res.setdefault("cases", {})
    todo = [c for c in cases if force or c["id"] not in cs or cs[c["id"]].get("key") != key_for(cfg, c)]
    if not todo:
        print(f"[{name}] niente da fare (risultati già salvati)")
        return
    print(f"[{name}] warm-up…")
    await run_case(cfg, cases[0])  # carica il modello in memoria, non conteggiato
    for c in todo:
        cs[c["id"]] = await run_case(cfg, c)
        r = cs[c["id"]]
        if r.get("error"):
            status = r["error"]
        elif not r["valid"]:
            status = "JSON non valido"
        else:
            p = score_case(c, r["out"])["pass"]
            status = "da leggere" if p is None else ("ok" if p else "FAIL")
        print(f"[{name}] {c['id']}: {status} ({r.get('sec', '-')} s)")


def pct(a, b):
    return "-" if not b else f"{100 * a / b:.0f}% ({a}/{b})"


def scores_for(by: dict, cs: dict) -> dict:
    """Punteggi ricalcolati dal testo salvato: se cambiano le regole non serve rifare le chiamate."""
    return {cid: score_case(by[cid], r["out"]) for cid, r in cs.items() if cid in by and r.get("valid")}


def report(cases, all_res, stale: dict | None = None) -> str:
    by = {c["id"]: c for c in cases}
    err_ids = [c["id"] for c in cases if c["error"] and not c.get("manual")]
    ctl_ids = [c["id"] for c in cases if not c["error"] and not c.get("manual")]
    man_ids = [c["id"] for c in cases if c.get("manual")]
    L = ["# Report benchmark LLM per il tutor", "",
         f"Modelli confrontati: {', '.join(all_res)}", "",
         "| Modello | JSON valido | Errori corretti bene | Errori rilevati | Controlli senza falsi allarmi | "
         "Spiegazioni in italiano | Risposta adatta al TTS | Parole nella risposta (mediana) | Latenza mediana | "
         "tok/s mediani | Troncati | Con thinking |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, res in all_res.items():
        cs = {k: v for k, v in res.get("cases", {}).items() if k in by}  # ignora casi non più nel file dei casi
        sc = scores_for(by, cs)
        ok = [c for c in cs.values() if c.get("valid")]
        e_pass = sum(1 for i in err_ids if i in sc and sc[i]["pass"])
        e_det = sum(1 for i in err_ids if i in sc and sc[i]["detected"])
        c_pass = sum(1 for i in ctl_ids if i in sc and sc[i]["pass"])
        expl = [sc[i]["explanation_it"] for i in err_ids if i in sc and sc[i]["explanation_it"] is not None]
        spk = [sc[i]["speakable"] for i in sc]
        words = [len(cs[i]["out"]["reply"].split()) for i in sc]
        secs = [c["sec"] for c in cs.values() if "sec" in c]
        trunc = sum(1 for c in cs.values() if c.get("finish") == "length")
        think = sum(1 for c in cs.values() if c.get("reasoning_chars", 0) > 0)
        tps = [c["tokens"] / c["sec"] for c in cs.values() if c.get("sec", 0) > 0 and c.get("tokens")]
        L.append(
            f"| {name} | {pct(len(ok), len(cs))} | {pct(e_pass, len(err_ids))} | {pct(e_det, len(err_ids))} | "
            f"{pct(c_pass, len(ctl_ids))} | {pct(sum(expl), len(expl))} | {pct(sum(spk), len(spk))} | "
            f"{statistics.median(words) if words else 0:.0f} | "
            f"{statistics.median(secs):.1f} s | {statistics.median(tps) if tps else 0:.0f} | {trunc} | {think} |"
            if secs else f"| {name} | nessun risultato |")
    for name, (old, missing) in (stale or {}).items():
        if old or missing:
            L += ["", f"> ⚠ **{name}**: {old} risultati ottenuti con un prompt/parametri diversi da quelli attuali e "
                      f"{missing} casi mancanti. Rilancia `--models {name}` prima di confrontarlo."]
    L += ["", "_Latenza = tempo totale per risposta (temperatura 0, nessuna storia). Per un tutor vocale conta "
          "restare entro pochi secondi. Le risposte lunghe (colonna «Parole») allungano il TTS e tendono a "
          "ripetere ciò che sta già nelle correzioni._", "", "## Dove sbagliano", ""]
    for name, res in all_res.items():
        L.append(f"### {name}")
        sc = scores_for(by, res.get("cases", {}))
        for cid, r in res.get("cases", {}).items():
            c = by.get(cid)
            if not c or c.get("manual"):
                continue
            if r.get("error"):
                L.append(f"- **{cid}** errore di chiamata: {r['error']}")
            elif not r.get("valid"):
                L.append(f"- **{cid}** JSON non valido: {r.get('parse_error')} · inizio risposta: `{r['raw'][:80]!r}`")
            elif not sc[cid]["pass"]:
                o = r["out"]
                L.append(f"- **{cid}** «{c['text']}» → is_correct={o['is_correct']}, corretta: «{o['corrected_sentence']}»; "
                         f"correzioni: " + "; ".join(f"{m['original']} → {m['corrected']}" for m in o["corrections"]))
        L.append("")
    if man_ids:
        L += ["## Da leggere a mano", "",
              "_Casi senza punteggio automatico: guarda se il tutor resta nel ruolo, aiuta davvero e non inventa errori._", ""]
        for cid in man_ids:
            L += [f"### {cid} · «{by[cid]['text']}»", f"_{by[cid].get('note', '')}_", ""]
            for name, res in all_res.items():
                r = res.get("cases", {}).get(cid)
                if r and r.get("valid"):
                    o = r["out"]
                    L += [f"**{name}**", f"- risposta: {o['reply']}",
                          f"- corretta: {o['corrected_sentence']} (is_correct={o['is_correct']})"]
                    L += [f"- correzione: {m['original']} → {m['corrected']}: {m['explanation_it']}" for m in o["corrections"]]
                    L += [f"- follow-up: {o['follow_up']}", ""]
    L += ["## Esempi completi da leggere (qualità dell'italiano e della conversazione)", ""]
    shown = [i for i in ("e01", "e05", "e16", "c07", "h01", "h03") if i in by]
    for cid in shown:
        for name, res in all_res.items():
            r = res.get("cases", {}).get(cid)
            if r and r.get("valid"):
                L += [f"**{name} · {cid}** · «{by[cid]['text']}»", "```json",
                      json.dumps(r["out"], ensure_ascii=False, indent=1), "```", ""]
    return "\n".join(L) + "\n"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", help="modelli da ESEGUIRE (il report include comunque tutti quelli con risultati)")
    ap.add_argument("--cases", default="cases.json", help="file dei casi (es. cases_hard.json)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    cases_path = ROOT / args.cases
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]
    cfgs = tomllib.loads((ROOT / "models.toml").read_text(encoding="utf-8"))["models"]
    to_run = args.models or list(cfgs)
    # il set di base salva in results/, gli altri in results/<nome-file>/ per non mescolare i risultati
    out_dir = ROOT / "results" if cases_path.stem == "cases" else ROOT / "results" / cases_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.report_only:
        for n in to_run:
            p = out_dir / f"{n}.json"
            res = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            await run_model(n, cfgs[n], cases, res, args.force)
            p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    all_res = {}
    for n in cfgs:  # nell'ordine di models.toml, tutti i modelli che hanno già risultati
        p = out_dir / f"{n}.json"
        if p.exists():
            res = json.loads(p.read_text(encoding="utf-8"))
            if res.get("cases"):
                all_res[n] = res
    if not all_res:
        sys.exit("Nessun risultato.")
    stale = {}
    for n, res in all_res.items():
        cs = res["cases"]
        old = sum(1 for c in cases if c["id"] in cs and cs[c["id"]].get("key") != key_for(cfgs[n], c))
        stale[n] = (old, sum(1 for c in cases if c["id"] not in cs))
    (out_dir / "report.md").write_text(report(cases, all_res, stale), encoding="utf-8")
    print(f"\nReport su {len(all_res)} modelli ({', '.join(all_res)}): {out_dir / 'report.md'}")


if __name__ == "__main__":
    asyncio.run(main())
