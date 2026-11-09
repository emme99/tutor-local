#!/usr/bin/env python3
"""Produce l'audio del benchmark fonetico: registra dal microfono o sintetizza.

Le registrazioni esistenti di `stt-bench` (`../stt-bench/recordings/mac`) coprono
gia' le frasi di `phrases.json`: questo script serve per nuove frasi, nuove
macchine o per uno smoke test senza microfono.

Uso (dal venv del backend):
    # sintesi espeak-ng (in dominio per il modello: utile solo come smoke test)
    python phonetic_bench/make_audio.py --tts espeak --ids en01 en02 --out-dir /tmp/phonetic_audio

    # registrazione dal microfono (il Terminale deve avere il permesso microfono)
    python phonetic_bench/make_audio.py --record --ids en01 --out-dir phonetic_bench/audio --seconds 8
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHRASES = ROOT / "stt-bench" / "phrases.json"


def to_16k_wav(src: str, out: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                    "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", out], check=True)


def record(text: str, out: str, seconds: float, device: str) -> None:
    """Registra dal microfono con ffmpeg (avfoundation su macOS)."""
    print(f"\nLeggi ad alta voce:\n  «{text}»\n")
    input(f"Premi INVIO per iniziare la registrazione ({seconds:.0f} s)... ")
    with tempfile.TemporaryDirectory() as tmp:
        raw = str(Path(tmp) / "take.m4a")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "avfoundation",
                        "-i", device, "-t", str(seconds), "-ac", "1", raw], check=True)
        to_16k_wav(raw, out)
    print(f"salvato: {out}")


def synthesize(text: str, out: str, engine: str) -> None:
    """Sintetizza con espeak-ng o con la voce macOS `say`."""
    with tempfile.TemporaryDirectory() as tmp:
        if engine == "espeak":
            raw = str(Path(tmp) / "ref.wav")
            subprocess.run(["espeak-ng", "-v", "en-us", "-w", raw, text], check=True)
        else:
            raw = str(Path(tmp) / "ref.aiff")
            subprocess.run(["say", "-o", raw, text], check=True)
        to_16k_wav(raw, out)
    print(f"salvato: {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phrases", type=Path, default=DEFAULT_PHRASES)
    parser.add_argument("--ids", nargs="+", required=True, help="id delle frasi (es. en01 pron03)")
    parser.add_argument("--out-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true", help="registra dal microfono")
    mode.add_argument("--tts", choices=("espeak", "say"), help="sintetizza (smoke test)")
    parser.add_argument("--seconds", type=float, default=8.0, help="durata registrazione (default 8 s)")
    parser.add_argument("--device", default=":0", help="input avfoundation (default ':0')")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg non trovato (brew install ffmpeg)")
        return 2
    if args.tts == "espeak" and not shutil.which("espeak-ng"):
        print("espeak-ng non trovato (brew install espeak-ng)")
        return 2

    phrases = {item["id"]: item for item in json.loads(args.phrases.read_text())["phrases"]}
    missing = [pid for pid in args.ids if pid not in phrases]
    if missing:
        print(f"id sconosciuti: {', '.join(missing)}")
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for pid in args.ids:
        text = phrases[pid]["text"]
        out = str(args.out_dir / f"{pid}.wav")
        if args.record:
            record(text, out, args.seconds, args.device)
        else:
            synthesize(text, out, args.tts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
