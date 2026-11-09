# stt-bench: Gemma 4 E4B vs il tuo STT (e Box su S26)

Mini progetto per confrontare motori di riconoscimento vocale sulle **stesse registrazioni**, tutto in locale sul Mac.
Misura: WER/CER per categoria, latenza (RTF), comportamento sulle clip >30 s, e due test sulla pronuncia.

## Setup

```bash
brew install ffmpeg
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
```
La prima esecuzione scarica i modelli Hugging Face (serve rete solo per quello).
Al Terminale va concesso il permesso microfono (Impostazioni → Privacy).

## Flusso

1. **Registra** (circa 15-20 min per 40 frasi + 8 take doppie di pronuncia):
   ```bash
   python record.py            # oppure: --only it_numbers en_pron pron01
   ```
   Leggi col tuo accento naturale. La lista completa è in `frasi.md`.
2. **Configura i motori** in `config.toml` (soprattutto `base_url` del tuo `openai-macos-stt-tts`).
3. **Esegui**:
   ```bash
   python run_bench.py                      # tutti i motori
   python run_bench.py --engines mio_stt gemma_verbatim
   ```
   I risultati sono salvati per motore in `results/mac/*.json` (si riprende da dove si era arrivati; `--force` per rifare).
4. **Leggi** `results/mac/report.md`.

## Box su S26 Ultra

Box non si può automatizzare dal Mac, quindi i suoi risultati si inseriscono a mano:

```bash
python run_bench.py --export-template box     # crea manual/box.csv
```
Compila la colonna `text` (e `translation` per le frasi che hanno una traduzione di riferimento), poi lancia `run_bench.py`: `box_s26` compare nel report accanto agli altri.

Per l'audio hai tre opzioni, in ordine di equità:
- **Stessi file**: se Box permette di caricare un file audio, usa i wav di `recordings/mac/`.
- **Riproduzione**: riproduci i wav dal Mac vicino al telefono (aggiunge rumore di altoparlante/ambiente a Box, quindi penalizza un po' il suo risultato).
- **Dal vivo**: leggi le frasi direttamente a Box (stesso parlante, ma audio diverso: le differenze piccole non sono significative).

Attenzione: Box e MLX possono usare **quantizzazioni e runtime diversi** dello stesso modello. Se i risultati differiscono, non puoi attribuire la differenza solo al modello.

## Cosa guardare nel report

- **WER per categoria**: dove sbaglia ciascun motore (numeri, nomi, termini tecnici, parlato spontaneo).
- **Clip lunghe**: Gemma ha un limite di 30 s per clip. `it20` dura circa 35-40 s e serve a vedere se tronca o fallisce.
- **Pronuncia A**: sulle take sbagliate di proposito, il motore scrive ciò che hai detto («sheep») o lo corregge («ship»)? Un motore *fedele* è più utile per un tutor.
- **Pronuncia B**: a Gemma si chiede quali parole sono pronunciate male. Conta i rilevati e, soprattutto, i **falsi allarmi** sulle take corrette.
- **Traduzione**: output dei motori che la supportano (Gemma), da leggere a mano.

## Limiti da tenere presenti

- 40 frasi e un solo parlante: indicano una tendenza, non una verità statistica. Più frasi → più affidabilità.
- Numeri e date: il riferimento ammette più forme (parole, cifre, 17:45). Se un motore usa una forma non prevista, può comparire un errore spurio: controlla il dettaglio.
- Le chiamate a `mlx_vlm` (`load`, `generate`, `apply_chat_template(..., num_audios=1)`) rispecchiano l'API che conosco, ma cambia tra versioni: se la tua differisce, il punto da toccare è `GemmaMLX._ask` in `run_bench.py` (poche righe).
- L'ID del modello MLX in `config.toml` va verificato su Hugging Face; con mlx-vlm < 0.5.0 l'audio può risultare corrotto.
- Il prompt `plain` è ispirato a quello della documentazione Gemma; `verbatim` chiede di non correggere nulla. Confrontarli è parte del test.
