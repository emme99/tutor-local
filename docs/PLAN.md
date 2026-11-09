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
- [x] Collaudo manuale in browser (suggested reply + drawer di ripasso): badge e IPA visibili, latenza percepita
      < 2 s. *Unica verifica che richiede una persona davanti allo schermo.*
- [x] Footprint stimato con i pesi su disco + misure reali: Qwen3.8-27B-Splash **16 GB** + Whisper MLX **~1,6 GB**
      + Wav2Vec2 **~2,2 GB** (driver MPS) ≈ **20 GB**, con margine per contesto/KV → **< 30 GB**. (Il runtime di
      Qwen non è stato misurato: Splash non era attivo; i 16 GB sono i pesi del checkpoint.)
- [x] Doc: TECHNICAL.md (§2 tabella componenti, §3 struttura, §5 API, §8 config e verifica end-to-end, §10.3 record
      della decisione con i dati del benchmark, §12 troubleshooting, §15 roadmap voce 1 → fatto), `.env.example`
      (`PHONETIC_MODEL`, `PHONETIC_DEVICE` già presenti), `GUIDA-STUDENTE.md` (score fonetico, badge, IPA, limiti,
      troubleshooting, checklist) e `README.md` (niente più riferimenti al confronto Whisper).
### Fase 5 — Feedback per parola, calibrazione e validazione
Obiettivo: passare da «un numero per la frase» a «dove sta l'errore», e validare lo score su dati nuovi.
**Prerequisiti**: Fasi 0–4 complete (collaudo manuale fatto il 2026-11-09).

**Esecuzione con contesto ridotto** (modello locale con poco contesto, es. Qwen3.8-27B in locale, o quota di
token limitata). Questa fase è pensata per essere eseguita a piccoli pezzi:
- **Una sessione per task**, sessione nuova per ciascuno, `git commit` a fine task. Se il contesto si esaurisce a
  metà, commit «WIP» e marca il task con `[~]` indicando in una riga cosa manca.
- **Non leggere tutto il piano**: `grep -n "^#### 5" PLAN-fonetica.md`, poi `sed -n '<da>,<a>p' PLAN-fonetica.md`
  solo per il task da eseguire e per la sezione «Decisioni» di questa fase.
- **Non aprire interi i file grandi** (`App.jsx`, `phonetics.py`, TECHNICAL.md): prima `grep -n` del simbolo o
  della stringa da toccare, poi lettura a intervalli di righe. Ogni task elenca i «File da leggere».
- **Documentazione per ultima**, in una sessione a sé (5.8), partendo da `git log --oneline` e
  `git diff --stat` per sapere cosa è cambiato.
- **Ordine consigliato**: 5.4c (solo CSS/markup) → 5.1 parte A (solo `align` e conteggi) → 5.4b →
  5.1 parte B (parole e dittonghi) → 5.2 → 5.3 → 5.4 → 5.5 → il resto.
- Prompt d'avvio suggerito: «Leggi solo il task <ID> e la sezione “Decisioni” di PLAN-fonetica.md (usa grep e
  sed, non aprire tutto il file) e i file indicati sotto “File da leggere”. Prima di modificare, riassumi in 5
  righe cosa farai. A fine task: file modificati, comandi eseguiti, esito dei test.»

**Perché (dati misurati; ricalcolati applicando l'algoritmo di `phonetics.py` all'esempio en02 qui sopra: distanza
10,0 su 55 simboli IPA atomici → 82, cioè il valore riportato dall'API. L'agente deve rileggere `phonetics.py` e
rifare il conto prima di modificarlo):**
- Su en02 il costo 10,0 si scompone in: 3,0 da sei sostituzioni vocaliche (0,5 ciascuna), 4,0 da quattro
  cancellazioni, 2,0 da due inserzioni, 1,0 dall'unica sostituzione consonantica (`ð→d` in *with*).
  L'errore consonantico tipico dell'italiano pesa ~1,8 punti su 100: invisibile nel numero.
- Due delle quattro cancellazioni sono la `ʊ` di `oʊ→o` (*tomorrow*, *so*): un dittongo è due simboli, quindi
  `oʊ→o` costa 1,0 (più di una sostituzione vocalica, 0,5) e pesa ~3,6 punti, il doppio dell'errore consonantico.
  È una distorsione di progetto, non di modello: l'accento italiano monottonga spesso i dittonghi, ma non è
  un errore grave quanto una consonante sbagliata.
- `matched_phones` vale `round(total_phones × score / 100)` (39 = 47 × 0,82): `total_phones` conta i *token*
  (47), mentre lo score usa i *simboli* (55). Non è un conteggio di fonemi allineati.
- Lo score assoluto sul parlato accentato non è calibrato: frasi pulite mediana 69, minimo 47, e le soglie del
  badge (70/45) sono tarate sugli stessi dati; per definizione di mediana, circa metà delle frasi corrette non
  è verde. Gate e soglie sono stati fissati *dopo* aver visto i dati, sulle stesse 11 frasi e 8 coppie
  (un parlante, una sessione): descrivono, non validano.
- La sensibilità sulle coppie minime (delta +33,5) non si trasferisce alle frasi (drop mediano +8 per una parola
  mancante, comparabile alla variabilità tra frasi): un errore puntuale in una frase intera non emerge dal numero.
  Serve segnalare *quale parola/fonema*.

**Decisioni**
- Il riferimento resta il **testo** (`phonemizer`); nessun audio sintetico come riferimento *né come «tetto» di
  calibrazione*: `say` è fuori dominio (32/100) ed espeak darebbe ~95 uniforme, quindi non calibrerebbe nulla sul
  parlato umano. L'idea di progresso personale (5.6) usa le prese precedenti dello stesso allievo, non l'audio TTS.
- **Nessuna chiamata all'LLM** in questa fase: consigli da tabella deterministica. Non si toccano `CONVERSATION`,
  `SCHEMA`, `system_prompt`, quindi l'impronta di `llm_bench` resta invariata.
- **Retrocompatibilità**: i campi esistenti di `PronunciationCheck` mantengono nome e significato (con la correzione
  dichiarata in 5.1 per `matched_phones`/`total_phones`); i nuovi campi (`words`, `issues`) sono additivi.
- **Protocollo di validazione**: i criteri di accettazione della 5.5 vanno scritti nel report **prima** di eseguire
  il set nuovo e non si ritara nulla sul set nuovo. Le soglie si scelgono sul set A (registrazioni esistenti) e si
  verificano sul set B (nuove registrazioni).
- **Niente `torchaudio`** (decisione della Fase 0): per la 5.7 si implementa un Viterbi CTC minimo con `numpy`/`torch`.

#### 5.1 Allineamento, parole e dittonghi (backend)
- [x] Rileggi `phonetics.py` e `tests/test_phonetics.py`; riporta in 5 righe cosa trovi (funzioni esistenti,
      punti in cui l'IPA è atomizzato, quali route/componenti usano `evaluate_pronunciation`).
- [x] `align(expected, predicted)`: stessa programmazione dinamica di `distance`, con backtrace che restituisce
      operazioni `match | sub | ins | del` con indici e costo. `distance` e `score` restano e devono dare gli stessi
      valori di prima su coppie fisse (test di equivalenza; en02 → 82).
- [x] Fonemizza **parola per parola** (`tokenizer.phonemize` su ogni parola), mantenendo la mappa
      simbolo → parola; gestisci punteggiatura, contrazioni e parole che producono sequenza vuota. Regola
      per le inserzioni: attribuite alla parola attesa precedente (o alla successiva se sono a inizio frase).
- [x] **Dittonghi come unità** nell'allineamento: insieme dati `DIPHTHONGS` (almeno `oʊ`, `aɪ`, `eɪ`, `aʊ`, `ɔɪ`)
      i cui token non si spezzano in simboli; sostituzione tra dittongo e vocale singola o tra dittonghi = costo
      vocalico (0,5), non una cancellazione intera. **Cambia lo score di en02 e delle altre frasi**: documenta il
      valore prima/dopo per tutte le frasi del set A (serve alla ritaratura in 5.5).
- [x] `matched_phones` e `total_phones` calcolati dalle operazioni, con lo stesso denominatore dello score
      (unità di allineamento attese); i nomi dei campi non cambiano.
- [x] Risposta additiva: `words: [{word, expected_ipa, heard_ipa, score, ops: [{op, expected, heard}]}]`.
- [x] `PHONETIC_MAX_SECONDS` (default 20): oltre, errore applicativo chiaro (stesso stile di `EmptyAudio`, HTTP 400)
      invece di rischiare memoria/latenza anomale su MPS.
- [x] Test puri senza modello, su sequenze IPA fisse: *ship/sheep*, *think/sink*, parola omessa, vocale aggiunta
      (*street* → *istreet*), frase identica = 100, frase vuota, en02 (distanza e score pre-fix riprodotti, poi
      il valore dopo il fix dei dittonghi).
- [x] Nessun import di `torch`/`transformers` fuori dalle funzioni che li richiedono (la suite resta offline).

#### 5.2 Normalizzazioni configurabili
- [ ] Variabili in `config.py`, `.env.example` e TECHNICAL.md §8: `PHONETIC_STRICTNESS` = `lenient` (default) |
      `strict`; `PHONETIC_VOWEL_COST` (default 0,5; in `strict` 1,0); `PHONETIC_KEEP_LENGTH` (default 0; in
      `strict` 1, quindi `ː` non si toglie); `PHONETIC_DISTINGUISH_R` (default 0: `ɹ`/`r` equivalenti).
- [ ] Con le impostazioni di default il comportamento resta quello attuale, **tranne** il trattamento dei
      dittonghi dichiarato in 5.1.
- [ ] Test per modalità: lo stesso confronto *ship/sheep* costa diversamente in `lenient` e in `strict`;
      `PHONETIC_DISTINGUISH_R=1` distingue `ɹ` da `r`.

#### 5.3 Consigli deterministici per l'italiano (`app/phonetic_tips.py`)
- [x] Tabella **dati** (dict/JSON, non logica sparsa): per ogni sostituzione/omissione/inserzione tipica, nome del
      suono, consiglio breve in italiano e peso di gravità. Almeno: `θ→t/s/f`, `ð→d/z`, `ɪ→i` e `ʊ→u`
      (vocali tese/lasse), `h` omessa, vocale aggiunta prima di *s*+consonante, terminazioni *-ed* (`t`/`d`/`ɪd`)
      omesse, vocale finale aggiunta dopo consonante (*dog* → *doga*), `ŋ→ŋg`/`n`, `ʒ/dʒ/ʃ/tʃ` scambiati.
- [x] Funzione che prende le operazioni della 5.1 e restituisce **al massimo 2** `issues`:
      `{word, expected, heard, tip_it, severity}`, ordinati per gravità (parola omessa e consonanti prima delle
      vocali; in `lenient` non segnalare differenze vocaliche lievi). Formulazione prudente («sembra che…»): il
      riconoscitore può sbagliare. Frase senza differenze significative → nessun `issue`.
- [x] Aggiungi `issues` alla risposta (additivo). Nessuna chiamata all'LLM.
- [x] Test per ogni voce della tabella e per il limite di 2; i testi italiani vanno rivisti dall'utente (H-5.3).

#### 5.4 Interfaccia di feedback
- [x] Componente dedicato (`frontend/src/PronunciationFeedback.jsx`, props → render) usato nei **due** punti
      esistenti di `App.jsx` (risposta suggerita e drawer di ripasso), senza ristrutturare il resto del file.
- [x] Parole in tre stati (ok / dubbio / da rivedere) derivati da `words` e `issues`, **non solo con il colore**
      (anche icona o sottolineatura); toccando una parola compaiono IPA atteso/sentito e il consiglio; al massimo
      2 consigli a schermo.
- [x] Il numero globale diventa secondario; scala qualitativa con le soglie ricalibrate in 5.5 (fino ad allora
      restano 70/45). Disclaimer: «indicazione automatica: può sbagliare; non valuta accento né prosodia».
- [x] Stati d'errore esistenti invariati («non ho sentito nulla», modello non disponibile, audio troppo lungo).
- [x] `npm run build` verde; collaudo manuale in browser (il collaudo della Fase 4 è già stato fatto: ripetere solo
      per le parti modificate).

#### 5.4b Scala per parole e frasi brevi
**Perché (verificato nello screenshot del collaudo, 2026-11-09):** il ripasso di *tower/towel* mostra atteso
`t aʊ əl`, pronunciato `t a b ɔ l`, badge **70/100 verde** e «Fonemi corretti (stima): 2/3». Applicando
l'algoritmo attuale: 5 simboli attesi (`t a ʊ ə l`), `ʊ→b` (vocale→consonante) 1,0, `ə→ɔ` 0,5, distanza 1,5
→ 1 − 1,5/5 = **70**. Su un bersaglio breve una sola consonante diversa basta per restare «verde»; le soglie
70/45 sono state tarate su frasi da ~40–55 simboli e non valgono qui. «2/3» è il conteggio derivato descritto
nell'allineamento 9.
**Decisioni**: per i bersagli brevi la scala è **qualitativa e basata sulle operazioni di allineamento**, non su
una percentuale. Nessuna eccezione ad hoc per parole specifiche (la sequenza `aʊ`+`əl` può produrre artefatti del
riconoscitore): l'incertezza si comunica nel testo guida. Il campo `score` resta invariato.
**File da leggere**: `backend/app/phonetics.py` (`evaluate_pronunciation`, `score`), `backend/app/schemas.py`
(`PronunciationCheck`), `backend/tests/test_phonetics.py`, `backend/tests/test_api.py::test_pronunciation_check`;
frontend: `grep -n "Fonemi corretti" frontend/src/App.jsx` (i due punti da modificare).
- [x] **Dipendenza**: richiede `align()` della 5.1 (parte A: funzione e test di equivalenza). Se non c'è ancora,
      eseguire prima quella parte.
- [x] Configurazione `PHONETIC_SHORT_MAX_UNITS` (default 8, unità attese dopo la normalizzazione; valore da
      tarare). Un bersaglio con questo numero di unità o meno è «breve» (parole singole, frasi cortissime).
- [x] Funzione pura `verdict(ops)` (in `phonetics.py`, senza modello) con regole esplicite e testabili:
      `ok` = nessuna differenza; `dubbio` = solo sostituzioni vocale↔vocale, nessuna inserzione/cancellazione;
      `da_rivedere` = almeno una sostituzione consonantica, una sostituzione vocale↔consonante, o una
      inserzione/cancellazione.
- [x] Risposta **additiva**: `short_target: bool`, `verdict` (`"ok" | "dubbio" | "da_rivedere"`, `null` per i
      bersagli lunghi fino alla 5.5) e `ops` (allineamento globale; la 5.1 lo riusa per costruire `words`).
      `score`, `matched_phones`, `total_phones`, `expected_ipa`, `predicted_ipa` non cambiano nome.
- [x] Interfaccia (nel componente della 5.4, oppure nei due punti di `App.jsx` se la 5.4 non è ancora fatta): per
      i bersagli brevi **niente badge percentuale e niente «Fonemi corretti (stima)»**; badge testuale con icona
      («✓ Ci sei» / «~ Dubbio» / «✗ Da rivedere», non solo colore) e le due righe IPA allineate tramite `ops`, con i
      simboli diversi evidenziati (grassetto/sottolineatura oltre al colore) e `—` dove manca un simbolo; riga
      «Differenze: ʊ→b, ə→ɔ».
- [x] Testo guida sotto il badge per `da_rivedere` sui bersagli brevi: «Il riconoscitore può sbagliare sulle parole
      brevi: riprova una volta e confronta.»; il pulsante «Ripeti» resta in evidenza.
- [x] Per i bersagli lunghi il numero resta, in secondo piano, finché la 5.5 non ricalibra le soglie.
- [x] Test (pytest, senza modello) su `verdict`: identico → ok; solo `ə→ɔ` → dubbio; `ʊ→b` (caso *towel*) →
      da_rivedere; `ð→d` → da_rivedere; inserzione → da_rivedere; cancellazione → da_rivedere; confine di
      `PHONETIC_SHORT_MAX_UNITS` (8 vs 9 unità). Test API con motore fonetico stubbato: nuovi campi presenti,
      vecchi invariati.
- [ ] **Accettazione**: il caso *tower/towel* (IPA dello screenshot, motore stubbato) restituisce
      `short_target=true` e `verdict="da_rivedere"` e l'interfaccia non mostra alcun badge verde;
      `pytest -q`, `ruff check app tests`, `npm run build` verdi. **Collaudo manuale**: ripasso con 2–3 parole
      brevi (una giusta, una con consonante sbagliata, una con differenza vocalica).
- [x] Documentazione (in 5.8 o a fine task): TECHNICAL.md §5, §9 e §10.3 (con il caso *towel* come motivazione),
      `GUIDA-STUDENTE.md` (significato dei tre stati; perché sulle parole brevi non c'è la percentuale).

#### 5.4c Layout dei drawer (nessun messaggio sotto il pannello)
**Perché (verificato nello screenshot del collaudo, 2026-11-09):** con il drawer di ripasso aperto (finestra di
circa 1100 px) il pannello si sovrappone alla colonna destra della chat. I messaggi dello studente, allineati a
destra, risultano tagliati («Yesterday I went to the cinema w», «I saw a new», «Yes, it was») e anche il campo di
scrittura in basso finisce sotto il pannello: proprio le frasi che l'allievo vuole confrontare con le correzioni.
**Decisioni**: modifica limitata a CSS e al markup minimo; nessun refactoring di `App.jsx`, nessuna dipendenza
nuova, nessun cambiamento di comportamento (apertura/chiusura, contenuti, stato del ripasso). Larghezza soglia
(1000 px) e larghezza del pannello (360–420 px) sono proposte da regolare a occhio.
**File da leggere**: `grep -rn "drawer" frontend/src` per trovare CSS e markup; poi solo gli intervalli di
righe interessati.
- [x] Riporta in 5 righe come sono posizionati oggi drawer e colonna chat (posizionamento, larghezza, z-index) e
      quali drawer esistono (ripasso, eventuale aiuto in italiano): la correzione vale per tutti.
- [x] Sopra la larghezza soglia: drawer **affiancato** nel layout (sidebar | chat con `flex: 1; min-width: 0` |
      drawer a larghezza fissa), così la colonna chat si restringe e nulla finisce sotto; il campo di scrittura sta
      nella stessa colonna della chat.
- [x] Sotto la soglia: drawer come overlay (o bottom sheet) con sfondo oscurato, chiusura con clic fuori, tasto
      `Esc` e pulsante ×; la chat non si sposta.
- [x] Messaggi: `max-width` in percentuale della colonna e `overflow-wrap: anywhere`; i messaggi allineati a destra
      restano allineati al bordo destro della colonna **visibile**.
- [x] Aprire e chiudere il drawer non deve far saltare la posizione di scroll della chat (preserva `scrollTop`
      se serve).
- [ ] **Accettazione (collaudo manuale)**: a ~1400, ~1100 e ~800 px con il drawer aperto nessun messaggio e nessun
      elemento del campo di scrittura è tagliato; chiusura con `Esc` e clic fuori; `npm run build` verde. Allegare
      due screenshot a ~1100 px (drawer aperto e chiuso).

#### 5.5 Banco di prova per parola e validazione su dati nuovi
- [ ] Estendi `phonetic_bench/`: `cases_words.json` con, per ogni registrazione, `bad_words` (le parole in cui
      c'è un errore noto: coppie `pron01–pron08` e gli errori già confermati da Whisper in en06/en07/en09) e le
      prese pulite senza errori. Il runner misura **sensibilità per parola** (la parola con errore compare tra
      le «da rivedere» o negli `issues`) e **falsi allarmi** (parole segnalate nelle prese pulite).
- [ ] **Stabilità**: stessa frase registrata 3 volte nella stessa sessione; riporta la variazione dello score tra
      prese (serve a decidere se ha senso mostrare differenze piccole, vedi 5.6).
- [ ] **Set B**: nuova sessione di registrazioni (altro giorno, possibilmente altra voce o altro microfono; vedi
      H-5.5) con errori deliberati tipici, non usata per tarare nulla.
- [ ] **Prima** di eseguire il set B, scrivi nel report i criteri di accettazione (proposta da confermare:
      sensibilità per parola ≥ 70 %; falsi allarmi mediani ≤ 1 parola per presa pulita; stabilità dello score
      entro ±8 punti sulle 3 prese). Poi esegui e riporta i numeri, anche se negativi.
- [ ] Ricalibra le soglie del badge/scala qualitativa sui dati del set A (es. con percentili delle prese pulite),
      verificale sul set B e riportale in TECHNICAL.md §10.3. Impronta dei risultati come nelle altre misure
      (modello, frasi, audio, parametri, strictness).
- [ ] Confronto `lenient` / `strict` sugli stessi dati, con la decisione motivata.

#### 5.6 (Opzionale) Progresso personale
Solo se 5.5 mostra stabilità sufficiente tra prese; altrimenti **non adottare** (decisione dell'utente).
- [ ] Tabella `pronunciation_attempts(id, ts, target_hash, target, score)` con migrazione idempotente
      (`PRAGMA user_version`); si salvano solo punteggio e IPA, **mai l'audio**.
- [ ] La risposta aggiunge `previous_best` (stessa frase); l'interfaccia mostra «+N rispetto alla volta scorsa»
      solo se la differenza supera la variabilità misurata in 5.5.
- [ ] Test su database temporaneo; nessun cambiamento ai default.

#### 5.7 (Sperimentale, dietro flag) Allineamento forzato con confidenza per fonema
- [ ] `PHONETIC_FORCED_ALIGN` (default 0). Dai logit (log-softmax) e dagli id dei fonemi attesi nel vocabolario
      del tokenizer, un allineamento CTC forzato (Viterbi minimo, `numpy`/`torch`, senza `torchaudio`) dà una
      confidenza per ogni fonema atteso. Fonemi assenti dal vocabolario (`<unk>`): segnalali e saltali.
- [ ] Test del Viterbi su esempi piccoli con risultato noto; output aggiuntivo `phones: [{symbol, word,
      confidence}]`, da usare solo come indizio («incerto») nei consigli.
- [ ] Confronto con la decodifica libera nel banco di prova (sensibilità e falsi allarmi per parola). Si adotta
      solo se migliora, per decisione dell'utente; altrimenti resta spento e documentato.

#### 5.8 Documentazione e chiusura
- [ ] TECHNICAL.md: §5 (campi `words` e `issues`, correzione di `matched_phones`/`total_phones`), §8 (variabili
      `PHONETIC_*`), §9 (nuova interfaccia), §10.3 (risultati set A e B, soglie, effetto del fix dei dittonghi,
      decisione `lenient`/`strict`), §11 (nuovo benchmark), §12 (troubleshooting: espeak-ng assente, checkpoint non
      scaricabile, MPS non disponibile, audio troppo lungo), §14 (download del modello da Hugging Face; il modello
      resta in memoria dopo il primo uso), §15 (roadmap).
- [ ] `GUIDA-STUDENTE.md` (nuovo feedback per parola, scala qualitativa, limiti) e `README.md`.
- [ ] `pytest -q`, `ruff check app tests` e build Vite verdi; **nessun numero di benchmark inventato o stimato**:
      i valori in §10.3 sono quelli misurati dall'utente.


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
