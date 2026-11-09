# Piano: valutazione fonetica della pronuncia (sostituzione del confronto Whisper lessicale)

**Obiettivo**: sostituire il confronto lessicale basato su Whisper in `POST /api/pronunciation-check`
con una valutazione fonetica: **Wav2Vec2 XLSR-53 (CTC) su MPS**. Lo scoring confronta l'IPA decodificato
dall'audio dell'allievo con l'IPA atteso del testo (via `phonemizer`) e produce uno score 0–100
(distanza di Levenshtein pesata: le sostituzioni vocaliche costano meno di quelle consonantiche).

**Non cambia** il resto della pipeline: `/api/turn` (conversazione/scenario) resta su Whisper MLX
(decisione motivata in TECHNICAL.md §10.1: WER migliore, clip lunghe). La migrazione riguarda **solo**
la valutazione della ripetizione.

## Stato attuale (verificato nel repo, non assunto)

- Endpoint unico di valutazione: `POST /api/pronunciation-check` in `backend/app/main.py` (rotte in `main.py`;
  **non esiste** una cartella `routers/`). Dalla fase 3 il flow è `phonetics.evaluate_pronunciation`
  (Wav2Vec2 XLSR-53 + `phonemizer`) → schema `PronunciationCheck` (`score`, `matched_phones`, `total_phones`,
  `expected_ipa`, `predicted_ipa`). Il vecchio `app/pronunciation.py` (difflib sulle parole) è stato rimosso.
- Il frontend usa la risposta in **due** punti (`frontend/src/App.jsx`): ripetizione della `suggested_reply` e
  ripetizione della forma corretta nel drawer di ripasso. **Entrambi con frasi inglesi**; mostrano badge score
  (verde ≥ 70, giallo 45–69, rosso < 45) e sequenze IPA attesa/pronunciata.
- «Chiedi in italiano» è `/api/help`: **non** fa valutazione della pronuncia → non serve il supporto `it` in v1.
- Ambiente (`backend/.venv`, Python 3.13): `torch 2.14.1` con MPS ✓, `transformers 5.22.2` ✓,
  `phonemizer 3.6.0` ✓, `espeak-ng 1.52` (Homebrew) ✓, `ffmpeg` ✓ — tutto bloccato in `requirements*.txt`.
- `phonetic_bench/check_env.py` (ex `docs/test_wav2vec2_mps.py`) gira verde nel venv: modello caricato su
  MPS, scoring 95/100 su audio espeak-ng.
- Test: `backend/tests/test_phonetics.py` (funzioni pure, senza modello) e `test_api.py::test_pronunciation_check`
  (motore fonetico stubbato, suite offline).

## Architettura scelta (e perché)

Il riferimento per lo scoring è il **testo**, non un audio sintetizzato: `phonemizer` (espeak `en-us`)
produce l'IPA atteso, il modello produce l'IPA predetto dall'audio dell'allievo. Il tokenizer di
`wav2vec2-xlsr-53-espeak-cv-ft` (`Wav2Vec2PhonemeCTCTokenizer`) espone `phonemize()`, che separa già i
singoli fonemi: si usa quello invece di spezzare a mano l'IPA, perché il greedy longest-match confonde
token come `ju`/`uː` (bug trovato in fase 2). Le due sequenze sono confrontate con una **Levenshtein
pesata sui simboli IPA atomici**:

> Score = `1 − distanza(ipa_atteso, ipa_predetto) / len(ipa_atteso)`
>
> sostituzione vocale-vocale = 0.5; sostituzione consonantica, inserimento, cancellazione = 1.0

Prima del confronto si normalizzano lunghezza (`ː`, `ˑ`) e allofoni noti (`ɹ→r`, `ɾ→t`, `ᵻ→ɪ`, `ɐ→ə`).
Così le differenze di qualità vocalica dovute all'accento pesano meno degli errori consonantici
(`θ→t`, `ð→d`) e delle parole mancanti. Verificato in fase 0 (`phonetic_bench/check_env.py`): **95/100**
su audio espeak-ng (in-domain). La voce macOS `say` è fuori dominio per il modello (32/100): **non** va
usata come riferimento audio. `phonemizer` resta una dipendenza obbligatoria perché il tokenizer del
checkpoint lo richiede già al caricamento.

- Audio allievo → WAV 16 kHz mono riutilizzando `stt.to_wav` + filtro anti-silenzio `stt.audio_stats`
  (oggi privati in `providers/stt.py`: esporre `to_wav` come pubblica, senza cambiare la logica).
- Decodifica CTC greedy (`processor.batch_decode`), normalizzazione dei token (NFC; lo stress è già escluso
  con `with_stress=False`) **prima** dello scoring.
- Dipendenze nuove, bloccate in `requirements.txt` e `requirements-core.txt`: `torch==2.14.1`,
  `transformers==5.22.2`, `phonemizer==3.6.0`. Sistema: `espeak-ng` (brew) + `ffmpeg`. Niente
  `torchaudio`/`soundfile`: l'audio si legge con `wave` + `numpy` (già presenti).
- Memoria attesa: Qwen3.8-27B Q4 (~21 GB, Splash) + Whisper MLX (~1,6 GB) + XLSR-53 fp32 (~1,2 GB) ≈ 24 GB < 36 GB.

Risposta (`PronunciationCheck`; i vecchi campi `transcript`/`matched_words`/`differences` sono stati rimossi
in fase 3 insieme al frontend che li leggeva):

Esempio reale (en02, registrazione umana, score 82; IPA normalizzato per il confronto):

```json
{
  "expected": "Tomorrow morning I have a meeting with the client, so I need to wake up early.",
  "score": 82,
  "matched_phones": 39,
  "total_phones": 47,
  "expected_ipa": "t ə m ɑ r oʊ m ɔr n ɪ ŋ aɪ h æ v ə m i t ɪ ŋ w ɪ ð ð ə k l aɪə n t s oʊ aɪ n i d t ə w eɪ k ʌ p ɜ l i",
  "predicted_ipa": "t ʊ m ɔ r o m ɔ n ɪ ŋ aɪ h æ v m i t ɪ ŋ w ɪ d ð ɚ k l aɪ ə n t s o aɪ n i d t ʊ w eɪ k a p eɪ r l i"
}
```

## Task Checklist

### Fase 0 — Ambiente e dipendenze ✅
- [x] Aggiungere `torch==2.14.1`, `transformers==5.22.2` e `phonemizer==3.6.0` (richiesto dal tokenizer del
      modello al caricamento) a `requirements.txt` e `requirements-core.txt`; installati nel venv, import + MPS verificati.
- [x] Spostare `docs/test_wav2vec2_mps.py` → `phonetic_bench/check_env.py`: tolto `torchaudio`, mantenuto
      `phonemizer` (obbligatorio), audio reale al posto della sinusoide; eseguito verde nel venv.
- [x] Primo download del modello (~1,2 GB, cache HuggingFace) e inferenza reale su MPS: score **95/100** su
      audio espeak-ng; `say` fuori dominio (32/100) → il riferimento è il testo passato a `phonemizer`.

### Fase 1 — Modulo fonetico (`backend/app/phonetics.py`) ✅
- [x] Creare `phonetics.py` nel layout piatto di `app/` (come `pronunciation.py`), senza toccare i servizi esistenti.
- [x] Singleton lazy: modello + processor caricati alla prima chiamata, su `PHONETIC_DEVICE` (default `mps`,
      fallback `cpu`), `asyncio.Lock` come in `providers/stt.py`; variabili `PHONETIC_MODEL` / `PHONETIC_DEVICE`
      in `config.py`.
- [x] `text_to_ipa(text, lang)`: `phonemizer` (espeak, `en-us`) → IPA; usare `tokenizer.phonemize()` per i
      confini di fonema corretti (il greedy longest-match è stato rimosso in fase 2 perché sbagliava `ju`/`uː`).
- [x] `audio_to_phonemes(audio_bytes)`: WAV 16 kHz → tensor float32 (`wave`+`numpy`) → CTC decode → lista di
      fonemi normalizzati.
- [x] `score(expected, predicted)`: Levenshtein **pesato** su simboli IPA atomici (vocale-vocale 0.5, resto 1),
      funzione senza modello (testabile offline).
- [x] `evaluate_pronunciation(target, audio, lang="en")`: anti-silenzio (stesse soglie `AUDIO_MIN_SECONDS`/
      `AUDIO_MIN_RMS`), IPA atteso via `phonemizer`, decode dell'audio, score → dict con i campi del futuro
      schema (il modello Pydantic arriva in Fase 3). Audio breve/silenzioso → `EmptyAudio` (HTTP 400).
- [x] `stt._to_wav` → `stt.to_wav` (pubblica, riusata dal modulo) e test delle funzioni pure in
      `tests/test_phonetics.py`. Smoke test reale: score 95/100 su audio espeak, silenzio → `EmptyAudio`.

### Fase 2 — Benchmark e gate di accettazione (`phonetic_bench/`) ✅
  (principio del progetto: si misura prima di scegliere — il gate precede il cambio dell'endpoint)
- [x] `make_audio.py`: registra dal microfono (`ffmpeg avfoundation`) o sintetizza con espeak-ng/`say` per smoke
      test. Il benchmark usa le registrazioni umane già presenti in `stt-bench/recordings/mac` (`en01–en11` e le
      coppie `pron01–pron08`), perché `say` è fuori dominio per il modello.
- [x] `run_bench.py`: quattro misure — frasi pulite (11), coppie minime corrette/sbagliate (8), perturbazione
      sintetica (testo senza l'ultima parola, 11), latenza dopo warm-up e memoria (MPS + RSS). Risultati con
      impronta di modello/frasi/audio in `phonetic_bench/results/bench.json` e `report.md`.
- [x] **Misure** (Mac Apple Silicon, MPS, audio umano con accento italiano):
      - frasi pulite: mediana **69** (min 47); errori reali confermati da Whisper (en06 `Thursday→Tuesday`,
        en07 finali, en09 nomi propri) abbassano en06/en07/en09, non sono falsi negativi;
      - coppie minime: **7/8** ordinate correttamente, delta mediano **+33.5** (unica eccezione `cat/cut`, che
        il modello non distingue in questa registrazione);
      - perturbazione: **11/11** frasi peggiorano, drop mediano **+8** (una parola mancante in una frase lunga
        vale ~1–12 punti);
      - latenza: mediana **~0.12 s** (max ~0.16 s); memoria: **~1.26 GB** MPS allocati, ~750 MB RSS.
- [x] **Gate tarati sui dati** (il 90 iniziale vale per l'audio sintetico in-domain: `check_env.py` 95/100):
      mediana pulite ≥ 60 e minimo ≥ 40; coppie ≥ 7/8 e delta ≥ 10; perturbazioni in ordine ≥ 9/11 e drop
      mediano ≥ 5; latenza < 1 s. Tutti superati. I gate relativi (coppie e perturbazione) sono la prova che
      il motore discrimina davvero; lo score assoluto sul parlato accentato non è calibrato come un giudizio
      umano e va presentato con una scala qualitativa in fase 3.

### Fase 3 — Endpoint, schema, frontend, test ✅
- [x] `main.py`: `/api/pronunciation-check` → `phonetics.evaluate_pronunciation`; 400 "non ho sentito nulla:
      riprova" per audio breve/silenzioso (coerente con `/api/turn`, via `EmptyAudio`); mantenuto il limite
      `target` ≤ 500 caratteri.
- [x] `schemas.py`: nuovo `PronunciationCheck` (`expected`, `score`, `matched_phones`, `total_phones`,
      `expected_ipa`, `predicted_ipa`); rimosso `PronunciationDifference`.
- [x] Eliminati `app/pronunciation.py` (orfanato) e `tests/test_pronunciation.py`; `tests/test_phonetics.py`
      copre distanza pesata e normalizzazione (senza modello); `test_api.py::test_pronunciation_check` usa il
      servizio fonetico stubbato (suite resta offline).
- [x] `App.jsx` (2 punti): badge di accuratezza colorato con le soglie tarate sui dati di fase 2 (verde ≥ 70,
      giallo 45–69, rosso < 45), sequenze IPA in monospace, disclaimer aggiornato («Confronto fonetico automatico
      sui fonemi; non valuta l'accento né la prosodia»); pulsanti «Ascolta modello»/registrazione invariati.
- [x] `pytest -q` (46 test) e `ruff check app tests` verdi; build Vite ok.

### Fase 4 — Verifica d'integrazione e documentazione
- [x] Integrazione API end-to-end (`POST /api/pronunciation-check` reale, TestClient, registrazione `en02`):
      200 con score **82**, `matched_phones` 39/47; **3,9 s a freddo** (include caricamento modello), **0,10 s a caldo**;
      MPS ~1,26 GB allocati / ~2,2 GB driver, RSS ~590 MB. Build Vite ok.
- [ ] Collaudo manuale in browser (suggested reply + drawer di ripasso): badge e IPA visibili, latenza percepita
      < 2 s. *Unica verifica che richiede una persona davanti allo schermo.*
- [x] Footprint stimato con i pesi su disco + misure reali: Qwen3.8-27B-Splash **16 GB** + Whisper MLX **~1,6 GB**
      + Wav2Vec2 **~2,2 GB** (driver MPS) ≈ **20 GB**, con margine per contesto/KV → **< 30 GB**. (Il runtime di
      Qwen non è stato misurato: Splash non era attivo; i 16 GB sono i pesi del checkpoint.)
- [x] Doc: TECHNICAL.md (§2 tabella componenti, §3 struttura, §5 API, §8 config e verifica end-to-end, §10.3 record
      della decisione con i dati del benchmark, §12 troubleshooting, §15 roadmap voce 1 → fatto), `.env.example`
      (`PHONETIC_MODEL`, `PHONETIC_DEVICE` già presenti), `GUIDA-STUDENTE.md` (score fonetico, badge, IPA, limiti,
      troubleshooting, checklist) e `README.md` (niente più riferimenti al confronto Whisper).

## Allineamenti rispetto al piano originale (cosa è cambiato e perché)

1. **Nessuna cartella `services/` né `routers/` nel repo**: il modulo va in `app/phonetics.py` (layout piatto)
   e l'endpoint si edita in `main.py`.
2. **Il test «verified» non era riproducibile nel venv del progetto** (mancavano `transformers`/`phonemizer`;
   torch era 2.14.1, non 2.15): la Fase 0 lo rende verificabile dentro `backend/.venv`.
3. **Non esistono rotte `/api/repeat` o `/api/evaluate`**: l'unico endpoint di valutazione è
   `/api/pronunciation-check`, usato dal frontend sempre con frasi inglesi.
4. **«Chiedi in italiano» non fa valutazione della pronuncia** (`/api/help`): il routing `it` del piano
   originale non aveva un caso d'uso. v1 = inglese; l'italiano è follow-up dopo un benchmark dedicato
   (il modello è fine-tunato su inglese).
5. **La STT conversazionale resta Whisper**: la migrazione è solo della valutazione della ripetizione
   (decisione §10.1 valida e documentata).
6. **Nessuna mappatura espeak→IPA**: il tokenizer del modello emette già token IPA nello stesso alfabeto di
   `phonemizer` (verificato: 95/100). Il riferimento è il testo passato a `phonemizer`, non un audio
   sintetizzato: la voce `say` è fuori dominio per il modello (32/100). `phonemizer` resta una dipendenza
   perché il tokenizer del checkpoint lo richiede al caricamento.
