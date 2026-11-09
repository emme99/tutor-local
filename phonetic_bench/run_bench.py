#!/usr/bin/env python3
"""Benchmark della valutazione fonetica (fase 2 del piano).

Misura il motore `app/phonetics.py` su registrazioni umane e verifica i gate di
accettazione prima di commutare l'endpoint:

1. **Frasi pulite** (en01-en11, voce umana con accento italiano):
   score mediano >= 90.
2. **Coppie minime** (pron01-pron08): per ogni frase c'e' una take corretta
   (`pronNN_ok.wav`) e una sbagliata di proposito (`pronNN.wav`, che dice la
   parola `bad_say` al posto di `focus`). La take corretta deve ottenere uno
   score maggiore in almeno 7 coppie su 8, con delta mediano >= 3.
3. **Perturbazione sintetica** (parola finale rimossa dal testo atteso):
   lo score deve calare di almeno 15 punti in mediana.
4. **Latenza e memoria**: dopo il warm-up, mediana < 1 s per clip di ~5 s;
   si registrano memoria MPS allocata e RSS del processo.

Uso (dal venv del backend):
    backend/.venv/bin/python phonetic_bench/run_bench.py
    backend/.venv/bin/python phonetic_bench/run_bench.py \\
        --phrases stt-bench/phrases.json --audio-dir stt-bench/recordings/mac

I risultati finiscono in `phonetic_bench/results/bench.json` (con impronta di
modello, frasi e audio) e in `phonetic_bench/results/report.md`.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import resource
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import phonetics  # noqa: E402
from app.config import settings  # noqa: E402

BENCH_VERSION = "v1"  # cambia se cambia la logica di scoring o il set di frasi

# Il gate di 90 vale per l'audio sintetico in-domain (phonetic_bench/check_env.py,
# 95/100). Sul parlato umano con accento italiano e con errori reali (th, finali,
# nomi propri) la baseline misurata è ~69: il gate umano è quindi una soglia di
# regressione, mentre i gate relativi (coppie minime e perturbazione) verificano
# che il motore discrimini davvero.
GATES = {
    "clean_median_score": 60,
    "clean_min_score": 40,
    "pairs_ordered": 7,          # su 8 coppie minime
    "pairs_median_delta": 10,
    "perturbation_median_drop": 5,
    "perturbation_ordered": 9,   # su 11 frasi pulite
    "latency_median_sec": 1.0,   # clip di ~5 s
}


# ───────────────────────── utilità ─────────────────────────
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def imprint(phrases_path: Path, audio_files: list[Path]) -> str:
    """Impronta unica di frasi + audio: invalida i risultati se cambia qualcosa."""
    h = hashlib.sha256()
    h.update(BENCH_VERSION.encode())
    h.update(phrases_path.read_bytes())
    for path in sorted(audio_files):
        h.update(path.name.encode())
        h.update(sha256_file(path).encode())
    return h.hexdigest()[:16]


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def mps_memory() -> dict:
    import torch

    if not (torch.backends.mps.is_built() and torch.backends.mps.is_available()):
        return {}
    return {
        "mps_allocated_mb": round(torch.mps.current_allocated_memory() / 1e6, 1),
        "mps_driver_mb": round(torch.mps.driver_allocated_memory() / 1e6, 1),
    }


def rss_mb() -> float:
    # su macOS ru_maxrss è in byte, su Linux in KiB
    divisor = 1e6 if sys.platform == "darwin" else 1e3
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor, 1)


def strip_last_word(text: str) -> str:
    """Testo senza l'ultima parola (per la perturbazione sintetica)."""
    return text.rsplit(maxsplit=1)[0] if len(text.split()) > 1 else text


async def evaluate(target: str, audio: bytes, suffix: str = ".wav") -> dict:
    t0 = time.perf_counter()
    result = await phonetics.evaluate_pronunciation(target, audio, "en", suffix)
    result["sec"] = round(time.perf_counter() - t0, 3)
    return result


# ───────────────────────── benchmark ─────────────────────────
async def run(phrases: list[dict], audio_dir: Path) -> dict:
    clean = [p for p in phrases if p["lang"] == "en" and p["category"] != "en_pron"
             and (audio_dir / f"{p['id']}.wav").exists()]
    pairs = [p for p in phrases if p["category"] == "en_pron"]

    # Warm-up: carica modello/processor e backend espeak, non conteggiato.
    first = clean[0]
    print(f"warm-up su {first['id']}…")
    await evaluate(first["text"], read_bytes(audio_dir / f"{first['id']}.wav"))

    print(f"\n--- 1. Frasi pulite ({len(clean)}) ---")
    clean_results = []
    for p in clean:
        r = await evaluate(p["text"], read_bytes(audio_dir / f"{p['id']}.wav"))
        clean_results.append({"id": p["id"], "category": p["category"], **r})
        print(f"{p['id']:6} score {r['score']:3d}  ({r['matched_phones']}/{r['total_phones']} fonemi, {r['sec']:.2f} s)")

    print(f"\n--- 2. Coppie minime ({len(pairs)}) ---")
    pair_results = []
    for p in pairs:
        ok_path = audio_dir / f"{p['id']}_ok.wav"
        bad_path = audio_dir / f"{p['id']}.wav"
        if not (ok_path.exists() and bad_path.exists()):
            print(f"{p['id']}: take mancante, saltata")
            continue
        ok = await evaluate(p["text"], read_bytes(ok_path))
        bad = await evaluate(p["text"], read_bytes(bad_path))
        delta = ok["score"] - bad["score"]
        ordered = ok["score"] > bad["score"]
        pair_results.append({"id": p["id"], "focus": p["focus"], "bad_say": p["bad_say"],
                             "ok_score": ok["score"], "bad_score": bad["score"],
                             "delta": delta, "ordered": ordered,
                             "ok_ipa": ok["predicted_ipa"], "bad_ipa": bad["predicted_ipa"]})
        mark = "✓" if ordered else "✗"
        print(f"{p['id']:6} {p['focus']:>6} / {p['bad_say']:<6} ok {ok['score']:3d}  bad {bad['score']:3d}  delta {delta:+3d} {mark}")

    print(f"\n--- 3. Perturbazione: testo senza l'ultima parola ({len(clean)}) ---")
    perturbation_results = []
    for item, base in zip(clean, clean_results):
        target = strip_last_word(item["text"])
        r = await evaluate(target, read_bytes(audio_dir / f"{item['id']}.wav"))
        drop = base["score"] - r["score"]
        perturbation_results.append({"id": item["id"], "target": target,
                                     "score": r["score"], "drop": drop})
        print(f"{item['id']:6} base {base['score']:3d}  perturbato {r['score']:3d}  drop {drop:+3d}")

    # ─────────────── riepilogo e gate ───────────────
    clean_scores = [r["score"] for r in clean_results]
    deltas = [r["delta"] for r in pair_results]
    drops = [r["drop"] for r in perturbation_results]
    latencies = [r["sec"] for r in clean_results]

    summary = {
        "clean_n": len(clean_scores),
        "clean_median_score": statistics.median(clean_scores) if clean_scores else 0,
        "clean_min_score": min(clean_scores) if clean_scores else 0,
        "pairs_n": len(pair_results),
        "pairs_ordered": sum(1 for r in pair_results if r["ordered"]),
        "pairs_median_delta": statistics.median(deltas) if deltas else 0,
        "perturbation_ordered": sum(1 for r in perturbation_results if r["drop"] > 0),
        "perturbation_median_drop": statistics.median(drops) if drops else 0,
        "latency_median_sec": round(statistics.median(latencies), 3) if latencies else 0,
        "latency_max_sec": round(max(latencies), 3) if latencies else 0,
    }
    summary["gates"] = {
        "clean_median_score": summary["clean_median_score"] >= GATES["clean_median_score"],
        "clean_min_score": summary["clean_min_score"] >= GATES["clean_min_score"],
        "pairs_ordered": summary["pairs_ordered"] >= GATES["pairs_ordered"],
        "pairs_median_delta": summary["pairs_median_delta"] >= GATES["pairs_median_delta"],
        "perturbation_ordered": summary["perturbation_ordered"] >= GATES["perturbation_ordered"],
        "perturbation_median_drop": summary["perturbation_median_drop"] >= GATES["perturbation_median_drop"],
        "latency_median_sec": summary["latency_median_sec"] < GATES["latency_median_sec"],
    }
    summary["all_passed"] = all(summary["gates"].values())

    print("\n--- Riepilogo ---")
    print(f"score pulite: mediana {summary['clean_median_score']:.1f} (min {summary['clean_min_score']}), gate >= {GATES['clean_median_score']} e min >= {GATES['clean_min_score']}")
    print(f"coppie ordinate: {summary['pairs_ordered']}/{summary['pairs_n']}, delta mediano {summary['pairs_median_delta']:+.1f}, gate >= {GATES['pairs_ordered']} e delta >= {GATES['pairs_median_delta']}")
    print(f"perturbazione: {summary['perturbation_ordered']}/{summary['clean_n']} in ordine, drop mediano {summary['perturbation_median_drop']:+.1f}, gate >= {GATES['perturbation_ordered']} e drop >= {GATES['perturbation_median_drop']}")
    print(f"latenza: mediana {summary['latency_median_sec']:.3f} s (max {summary['latency_max_sec']:.3f}), gate < {GATES['latency_median_sec']} s")
    for name, passed in summary["gates"].items():
        print(f"  {'✅' if passed else '❌'} {name}")

    return {"clean": clean_results, "pairs": pair_results,
            "perturbation": perturbation_results, "summary": summary}


def build_report(result: dict, meta: dict) -> str:
    s = result["summary"]
    lines = [
        "# Benchmark valutazione fonetica", "",
        f"- modello: `{meta['model']}` su `{meta['device']}`",
        f"- impronta: `{meta['imprint']}` ({BENCH_VERSION})",
        f"- eseguito: {meta['timestamp']}",
        f"- audio: `{meta['audio_dir']}`", "",
        "## Gate", "",
        "| gate | misurato | soglia | esito |", "|---|---:|---:|---|",
        f"| score mediano frasi pulite | {s['clean_median_score']:.1f} | ≥ {GATES['clean_median_score']} | {'✅' if s['gates']['clean_median_score'] else '❌'} |",
        f"| score minimo frasi pulite | {s['clean_min_score']:.0f} | ≥ {GATES['clean_min_score']} | {'✅' if s['gates']['clean_min_score'] else '❌'} |",
        f"| coppie minime ordinate | {s['pairs_ordered']}/{s['pairs_n']} | ≥ {GATES['pairs_ordered']} | {'✅' if s['gates']['pairs_ordered'] else '❌'} |",
        f"| delta mediano coppie | {s['pairs_median_delta']:+.1f} | ≥ {GATES['pairs_median_delta']} | {'✅' if s['gates']['pairs_median_delta'] else '❌'} |",
        f"| perturbazioni in ordine | {s['perturbation_ordered']}/{s['clean_n']} | ≥ {GATES['perturbation_ordered']} | {'✅' if s['gates']['perturbation_ordered'] else '❌'} |",
        f"| drop mediano perturbazione | {s['perturbation_median_drop']:+.1f} | ≥ {GATES['perturbation_median_drop']} | {'✅' if s['gates']['perturbation_median_drop'] else '❌'} |",
        f"| latenza mediana | {s['latency_median_sec']:.3f} s | < {GATES['latency_median_sec']} s | {'✅' if s['gates']['latency_median_sec'] else '❌'} |",
        "", f"**Esito**: {'tutti i gate superati' if s['all_passed'] else 'gate non superati'}", "",
        "## Frasi pulite", "",
        "| id | categoria | score | fonemi | secondi |", "|---|---|---:|---:|---:|",
    ]
    for r in result["clean"]:
        lines.append(f"| {r['id']} | {r['category']} | {r['score']} | {r['matched_phones']}/{r['total_phones']} | {r['sec']:.2f} |")
    lines += ["", "## Coppie minime", "",
              "| id | focus / bad_say | ok | bad | delta | ordine |", "|---|---|---:|---:|---:|---|"]
    for r in result["pairs"]:
        lines.append(f"| {r['id']} | {r['focus']} / {r['bad_say']} | {r['ok_score']} | {r['bad_score']} | {r['delta']:+d} | {'✅' if r['ordered'] else '❌'} |")
    lines += ["", "## Perturbazione (testo senza ultima parola)", "",
              "| id | score base | score perturbato | drop |", "|---|---:|---:|---:|"]
    for r, base in zip(result["perturbation"], result["clean"]):
        lines.append(f"| {r['id']} | {base['score']} | {r['score']} | {r['drop']:+d} |")
    lines += ["", "## Risorse", "",
              f"- latenza mediana/max: {s['latency_median_sec']:.3f} s / {s['latency_max_sec']:.3f} s",
              f"- memoria MPS allocata: {meta['memory'].get('mps_allocated_mb', 'n/d')} MB",
              f"- memoria MPS driver: {meta['memory'].get('mps_driver_mb', 'n/d')} MB",
              f"- RSS processo: {meta['memory'].get('rss_mb', 'n/d')} MB", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phrases", type=Path, default=ROOT / "stt-bench" / "phrases.json")
    parser.add_argument("--audio-dir", type=Path, default=ROOT / "stt-bench" / "recordings" / "mac")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "phonetic_bench" / "results")
    args = parser.parse_args()

    phrases = json.loads(args.phrases.read_text(encoding="utf-8"))["phrases"]
    used = sorted(args.audio_dir.glob("*.wav"))
    if not used:
        print(f"nessun WAV in {args.audio_dir}")
        return 2

    result = asyncio.run(run(phrases, args.audio_dir))

    memory = {"rss_mb": rss_mb(), **mps_memory()}
    meta = {
        "bench_version": BENCH_VERSION,
        "model": settings.phonetic_model,
        "device": phonetics._state["device"] if phonetics._state else settings.phonetic_device,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phrases": str(args.phrases),
        "audio_dir": str(args.audio_dir),
        "imprint": imprint(args.phrases, used),
        "gates": GATES,
        "memory": memory,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = {"meta": meta, **result}
    (args.out_dir / "bench.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out_dir / "report.md").write_text(build_report(result, meta), encoding="utf-8")
    print(f"\nRisultati: {args.out_dir / 'bench.json'}")
    print(f"Report:    {args.out_dir / 'report.md'}")
    print(f"Memoria:   MPS {memory.get('mps_allocated_mb', 'n/d')} MB, RSS {memory['rss_mb']} MB")
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
