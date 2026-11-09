#!/usr/bin/env python3
"""Registra le frasi di phrases.json dal microfono del Mac (WAV 16 kHz mono).

Uso:
  python record.py                       # tutte le frasi
  python record.py --only it_tech pron01 en   # per id, categoria o lingua
  python record.py --overwrite          # rifai anche quelle già registrate

Output: recordings/<set>/<id>.wav
Per le frasi 'en_pron' vengono registrate due take:
  <id>_ok.wav  = pronuncia corretta
  <id>.wav     = pronuncia sbagliata di proposito
"""
import argparse
import json
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

SR = 16000
ROOT = Path(__file__).parent
LANG_LABEL = {"it": "ITALIANO", "en": "INGLESE (col tuo accento naturale)"}


def take(label: str) -> np.ndarray:
    chunks = []

    def cb(indata, frames, time_info, status):
        chunks.append(indata.copy())

    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb):
        input(f"   ● REC ({label}) — parla, poi premi INVIO per fermare ")
    return np.concatenate(chunks) if chunks else np.zeros((0, 1), dtype="float32")


def record_one(path: Path, label: str) -> bool:
    while True:
        input(f"   Premi INVIO per iniziare ({label}) ")
        audio = take(label)
        cut = int(0.15 * SR)  # toglie il "clic" del tasto INVIO
        if len(audio) > 2 * cut:
            audio = audio[:-cut]
        dur = len(audio) / SR
        peak = float(np.abs(audio).max()) if len(audio) else 0.0
        warn = ""
        if peak < 0.03:
            warn = "  ⚠ volume molto basso"
        elif peak > 0.99:
            warn = "  ⚠ clipping, allontanati dal microfono"
        ans = input(f"   {dur:.1f} s{warn} — INVIO = ok, r = rifai, s = salta: ").strip().lower()
        if ans == "r":
            continue
        if ans == "s":
            return False
        sf.write(str(path), audio, SR)
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="id, categorie o lingue (it/en)")
    ap.add_argument("--set", default="mac", help="nome della cartella in recordings/")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    items = json.loads((ROOT / "phrases.json").read_text(encoding="utf-8"))["phrases"]
    if args.only:
        sel = set(args.only)
        items = [i for i in items if i["id"] in sel or i["category"] in sel or i["lang"] in sel]

    out = ROOT / "recordings" / args.set
    out.mkdir(parents=True, exist_ok=True)

    print(f"Salvo in {out}. Ctrl-C per interrompere: quanto registrato resta salvato.\n")
    try:
        for n, it in enumerate(items, 1):
            if it["category"] == "en_pron":
                tasks = [
                    (out / f"{it['id']}_ok.wav", "pronuncia CORRETTA"),
                    (out / f"{it['id']}.wav",
                     f"SBAGLIATA di proposito: dì «{it['bad_say']}» al posto di «{it['focus']}»"),
                ]
            else:
                tasks = [(out / f"{it['id']}.wav", "lettura normale")]

            pending = [t for t in tasks if args.overwrite or not t[0].exists()]
            if not pending:
                continue

            print(f"[{n}/{len(items)}] {it['id']} · {it['category']} · {LANG_LABEL[it['lang']]}")
            print(f"   «{it['text']}»")
            for path, label in pending:
                if record_one(path, label):
                    print(f"   → salvato {path.name}\n")
                else:
                    print("   → saltato\n")
    except KeyboardInterrupt:
        print("\nInterrotto.")


if __name__ == "__main__":
    main()
