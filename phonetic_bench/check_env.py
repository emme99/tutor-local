#!/usr/bin/env python3
"""Verifica dell'ambiente per la valutazione fonetica (fase 0 del piano).

Controlla MPS, le dipendenze di sistema (ffmpeg, espeak-ng), carica
facebook/wav2vec2-xlsr-53-espeak-cv-ft su MPS e valida la pipeline di scoring:

    atteso    = phonemizer(testo, espeak, en-us)  -> IPA -> token del modello
    predetto  = modello(audio 16 kHz)             -> token IPA
    score     = 1 - Levenshtein(atteso, predetto) / len(atteso)

Il tokenizer del modello (`Wav2Vec2PhonemeCTCTokenizer`) emette già token IPA
nello stesso alfabeto di espeak/phonemizer: nessuna mappatura. `phonemizer`
è comunque richiesto dal tokenizer stesso al caricamento.

Nota: il modello è fine-tunato su audio espeak, quindi decodifica meglio
l'audio espeak-ng che la voce macOS `say` (usata solo come confronto).

Uso (dal venv del backend):
    backend/.venv/bin/python phonetic_bench/check_env.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unicodedata
import wave
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    import torch

MODEL_ID = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
SAMPLE_RATE = 16000
PHRASE = "I went to the cinema yesterday"


def check_system() -> None:
    print("--- 1. Dipendenze di sistema ---")
    missing = [name for name in ("ffmpeg", "espeak-ng") if not shutil.which(name)]
    if missing:
        print(f"❌ Mancano: {', '.join(missing)} (brew install {' '.join(missing)})")
        sys.exit(1)
    for name in ("ffmpeg", "espeak-ng"):
        print(f"✅ {name}: {shutil.which(name)}")


def check_mps() -> "torch.device":
    import torch

    print("\n--- 2. PyTorch e MPS ---")
    if not (torch.backends.mps.is_built() and torch.backends.mps.is_available()):
        print("❌ MPS non disponibile in questa build di PyTorch.")
        sys.exit(1)
    device = torch.device("mps")
    print(f"✅ PyTorch {torch.__version__}, device {device}")
    return device


def synth(text: str, out_wav: str, engine: str) -> None:
    """Sintetizza `text` in WAV 16 kHz mono usando `say` oppure `espeak-ng`."""
    with tempfile.TemporaryDirectory() as tmp:
        if engine == "say":
            raw = str(Path(tmp) / "ref.aiff")
            subprocess.run(["say", "-o", raw, text], check=True)
        else:
            raw = str(Path(tmp) / "ref.wav")
            subprocess.run(["espeak-ng", "-v", "en-us", "-w", raw, text], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
                        "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", out_wav],
                       check=True)


def load_wav(path: str) -> "np.ndarray":
    import numpy as np

    with wave.open(path, "rb") as w:
        assert w.getframerate() == SAMPLE_RATE, f"campionamento inatteso: {w.getframerate()}"
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def levenshtein(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def main() -> None:
    check_system()
    device = check_mps()

    import torch
    from phonemizer import phonemize
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

    print(f"\n--- 3. Caricamento modello {MODEL_ID} su MPS ---")
    processor = Wav2Vec2Processor.from_pretrained(MODEL_ID)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID).to(device)
    model.eval()
    params = sum(p.numel() for p in model.parameters())
    print(f"✅ Modello caricato ({params / 1e6:.0f} M parametri, fp32 su {device})")

    # Token IPA del modello: servono per spezzare l'IPA di phonemizer (parole intere)
    # in token dello stesso alfabeto prodotto dalla decodifica CTC.
    vocab = sorted((t for t in processor.tokenizer.get_vocab() if not t.startswith("<")), key=len, reverse=True)

    def split_ipa(word: str) -> list[str]:
        out, i = [], 0
        while i < len(word):
            for token in vocab:
                if word.startswith(token, i):
                    out.append(token)
                    i += len(token)
                    break
            else:
                out.append(word[i])
                i += 1
        return out

    def expected_tokens(text: str) -> list[str]:
        ipa = phonemize(text, language="en-us", backend="espeak", strip=True, with_stress=False)
        return [t for word in ipa.split() for t in split_ipa(word)]

    def predicted_tokens(wav_path: str) -> list[str]:
        inputs = processor(load_wav(wav_path), sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with torch.inference_mode():
            logits = model(inputs.input_values.to(device)).logits
        return processor.batch_decode(logits.argmax(dim=-1))[0].split()

    print("\n--- 4. Scoring: phonemizer (atteso) vs modello (predetto) ---")
    print(f"Frase: {PHRASE!r}")
    expected = [unicodedata.normalize("NFC", t) for t in expected_tokens(PHRASE)]
    with tempfile.TemporaryDirectory() as tmp:
        for engine in ("espeak-ng", "say"):
            wav = str(Path(tmp) / f"{engine}.wav")
            synth(PHRASE, wav, engine)
            predicted = [unicodedata.normalize("NFC", t) for t in predicted_tokens(wav)]
            if not predicted:
                print(f"❌ {engine}: il modello non ha prodotto fonemi.")
                sys.exit(1)
            distance = levenshtein(expected, predicted)
            score = round((1 - distance / len(expected)) * 100)
            note = "in dominio" if engine == "espeak-ng" else "fuori dominio (voce macOS)"
            print(f"{engine:9} → score {score:3d} ({note})")
            if engine == "espeak-ng":
                print(f"            atteso:   {' '.join(expected)}")
                print(f"            predetto: {' '.join(predicted)}")

    print("\n🎉 AMBIENTE PRONTO: Wav2Vec2 gira su MPS e la pipeline di scoring funziona.")


if __name__ == "__main__":
    main()
