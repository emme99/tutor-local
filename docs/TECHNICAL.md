# tutor-local: descrizione tecnica

Tutor vocale italiano → inglese, **interamente locale**: ascolta (Whisper), ragiona (LLM), parla (TTS).
Questo documento serve a chi riprenderà il progetto: architettura, contratti, decisioni (con i dati che le hanno motivate),
limiti noti e strada per le evoluzioni. Stato al momento della scrittura: MVP funzionante usato dal committente su un
MacBook Pro M3 Max (36 GB).

---

## 1. Principi di progetto

1. **Local-first**: nessun dato lascia la macchina. Tutti i servizi sono processi locali.
2. **Orchestrator, non agente**: il backend decide il flusso (STT → LLM → TTS); l'LLM non sceglie strumenti. Una sola chiamata
   LLM per turno: prevedibile, veloce, facile da testare.
3. **Provider intercambiabili**: LLM e TTS parlano API OpenAI-compatible; cambiare modello o server = cambiare variabili d'ambiente.
4. **Si misura prima di scegliere**: STT e LLM sono stati scelti con benchmark riproducibili (§10), non a sensazione.
5. **Il benchmark usa lo stesso prompt dell'app** (tranne la persona «Alex»), così i risultati valgono per il prodotto reale.

## 2. Architettura

```mermaid
sequenceDiagram
  participant B as Browser (React)
  participant A as FastAPI (orchestrator)
  participant S as Whisper (MLX, in-process)
  participant L as LLM (Ollama / Splash)
  participant T as TTS (openai-macos-stt-tts)
  B->>B: MediaRecorder + VAD (stop al silenzio)
  B->>A: POST /api/turn (audio webm, modalità, livello)
  A->>A: ffmpeg → WAV 16 kHz; scarta audio breve/silenzioso
  A->>S: trascrivi (lingua forzata)
  S-->>A: testo
  A->>L: chat/completions (prompt di modalità + storia + testo)
  L-->>A: JSON del tutor
  A->>T: /audio/speech (reply + follow_up)
  T-->>A: audio (mp3)
  A->>A: salva turno, errori, vocabolario (SQLite)
  A-->>B: JSON (trascrizione, tutor, audio base64, tempi)
```

| Componente | Tecnologia | Dove gira | Note |
|---|---|---|---|
| Interfaccia | React 18 + Vite | Browser | Un solo componente (`App.jsx`) + `vad.js` |
| Orchestrator | FastAPI + uvicorn (Python ≥ 3.11) | Processo locale, porta 8010 | Serve anche il frontend compilato |
| STT | `mlx-whisper`, `whisper-large-v3-turbo` | In-process nel backend (GPU Apple) | Alternativa: endpoint OpenAI-compatible |
| LLM | Gemma 4 26B-A4B (Ollama) — alternativa Qwen3.6-35B-A3B (Splash) | Server separato | `LLM_BASE_URL`, `LLM_MODEL` |
| TTS | `openai-macos-stt-tts` (comando `say` di macOS) | Server separato, porta 5050 | Facoltativo |
| Memoria | SQLite (`data/tutor.db`) | File locale | Turni, errori, vocabolario |

Tempi misurati nell'app (turno tipico, Gemma 26B-A4B): **STT ≈ 0,55 s · LLM ≈ 0,9-1,1 s · TTS ≈ 1,0 s → ≈ 2,6 s** dalla fine
del parlato alla voce del tutor. Un outlier a 6,9 s (LLM) è compatibile con il ricaricamento del modello da parte di Ollama
dopo il timeout di inattività (vedi §12).

## 3. Struttura del repository

```
backend/
  requirements.txt            dipendenze complete (include mlx-whisper, solo Apple Silicon)
  requirements-core.txt       senza mlx-whisper (Linux/Docker, STT_BACKEND=openai)
  app/
    main.py                   rotte HTTP, CORS, mount del frontend compilato
    orchestrator.py           flusso del turno (STT→LLM→TTS→memoria)
    modes.py                  prompt di sistema per modalità + persona + lingua della voce
    schemas.py                modelli Pydantic: TutorOutput, TurnResponse
    config.py                 variabili d'ambiente (.env) → Settings
    memory.py                 SQLite: storia, errori, vocabolario
    jsonparse.py              estrazione robusta del JSON dall'output dell'LLM (senza dipendenze)
    providers/stt.py          ffmpeg, filtro silenzio, backend mlx | openai
    providers/llm.py          client chat/completions, retry sul JSON non valido
    providers/tts.py          client /audio/speech
frontend/
  src/App.jsx                 interfaccia, registrazione, riproduzione, modalità
  src/vad.js                  VAD a energia (stop automatico al silenzio)
llm_bench/                    benchmark LLM per il compito del tutor (§11)
deploy/                       Dockerfile e compose (bozze non testate, §13)
docs/TECHNICAL.md             questo file
run.sh                        avvio in un solo processo
.env.example                  tutte le variabili configurabili
```

## 4. Flusso di un turno (dettaglio)

`orchestrator.run_turn(session_id, mode, level, spoken_lang, text|audio, speak)`:

1. **Ingresso**: se c'è `text` lo si usa così; se c'è `audio` → `stt.transcribe`. Nessuno dei due → `EmptyInput` (HTTP 400).
2. **STT** (`providers/stt.py`):
   - ffmpeg converte il contenuto (webm/mp4 del browser) in WAV 16 kHz mono 16 bit (via file temporanei).
   - `audio_stats` calcola durata e RMS. Se `durata < AUDIO_MIN_SECONDS` (0,4 s) o `RMS < AUDIO_MIN_RMS` (0,004) → testo vuoto
     → `EmptyInput("non ho sentito nulla: riprova")`. Motivo: Whisper su silenzio/clip brevissime inventa frasi («Thank you.»,
     «Grazie.») — osservato nei test.
   - Backend `mlx`: `mlx_whisper.transcribe(..., language=spoken_lang, condition_on_previous_text=False)`, serializzato da un
     `asyncio.Lock` (una sola trascrizione alla volta sulla GPU). Backend `openai`: POST multipart a `/audio/transcriptions`.
3. **Prompt**: `modes.app_system_prompt(mode, level, spoken_lang)` (§7) + storia (`memory.history(session, mode)`, ultimi
   `HISTORY_TURNS`=6 turni, dove l'assistente è rappresentato dal proprio JSON per mantenere il formato).
4. **LLM**: `llm.tutor_reply` → `chat/completions` non in streaming, con `response_format: json_object` (se `LLM_JSON_MODE=1`)
   e `reasoning_effort: "none"`. Parsing con `extract_json` (toglie `<think>…</think>`, code fence, testo attorno) e validazione
   Pydantic. Se fallisce: **un** retry con «Reply again with ONLY the JSON object»; se la risposta era troncata
   (`finish_reason == "length"`) l'errore dice che probabilmente il thinking è attivo.
5. **Normalizzazione**: `tutor.is_correct = not tutor.corrections`. Il modello a volte mette `is_correct=false` senza correzioni
   (2 casi su 48 nei test): per l'allievo conta solo ciò che viene mostrato.
6. **TTS** (se `speak` e `TTS_BASE_URL`): si pronuncia `reply` + `follow_up` (in conversazione e scenario; in traduzione il
   `follow_up` è una nota in italiano e non si legge). Un errore del TTS non fa fallire il turno (log + risposta senza audio).
7. **Persistenza** e risposta (`TurnResponse`).

## 5. API HTTP

Base: `http://127.0.0.1:8010`. Nessuna autenticazione (solo localhost, §14).

| Metodo | Percorso | Corpo | Risposta |
|---|---|---|---|
| GET | `/api/health` | — | `{llm:{base_url,model}, stt_model, tts_enabled}` |
| POST | `/api/turn` | `multipart/form-data`: `session_id`, `mode` (`conversation`\|`scenario`\|`translate`), `level` (A2…C1), `spoken_lang` (`en`\|`it`), `text?`, `audio?` (file), `speak?` (bool, default true) | `TurnResponse` |
| POST | `/api/translate` | JSON `{text, target:"it"\|"en"}` | `{translation}` (non salva nulla) |
| POST | `/api/speak` | JSON `{text, lang}` | `{audio_b64, audio_mime}` |
| GET | `/api/vocab` | — | elenco `{term, translation_it, example, first_seen, seen}` |
| GET | `/api/mistakes` | — | elenco `{ts, session, original, corrected, type, explanation_it}` |

`TurnResponse`:

```json
{
  "session_id": "uuid", "mode": "conversation", "transcript": "i went to milan last week",
  "tutor": {
    "is_correct": true, "corrected_sentence": "…",
    "corrections": [{"original":"…","corrected":"…","explanation_it":"…","type":"grammar"}],
    "reply": "That sounds wonderful!", "new_vocab": [{"term":"…","translation_it":"…","example":"…"}],
    "follow_up": "What was your favourite place?"
  },
  "audio_b64": "…", "audio_mime": "audio/mpeg",
  "timings": {"stt": 0.55, "llm": 0.98, "llm_tok_s": 64.7, "tts": 1.05}
}
```

Errori: `400` input non valido o nulla da trascrivere; `502` LLM/TTS non raggiungibile, risposta HTTP non valida o JSON non
conforme; `500` problemi locali (ffmpeg assente, STT mal configurato). Il messaggio è in `detail` e il frontend lo mostra.
`llm_tok_s` = token generati / tempo LLM totale (include il prefill: sottostima la velocità pura).

## 6. Modello dati (SQLite, `DB_PATH`, default `data/tutor.db`)

```sql
turns(id, ts, session, mode, transcript, tutor_json)            -- storia; tutor_json = TutorOutput serializzato
mistakes(id, ts, session, original, corrected, type, explanation_it)
vocab(term PRIMARY KEY, translation_it, example, first_seen, seen)  -- term in minuscolo; seen++ se si ripresenta
```
Le tabelle si creano da sole. La storia è filtrata per `session` **e** `mode`. `mistakes` e `vocab` sono già popolati ma non
ancora usati per il ripasso (§15).

## 7. Prompt e contratto JSON

### 7.1 Schema (stesso per tutte le modalità: un solo parser)
`is_correct`, `corrected_sentence`, `corrections[]` (`original`, `corrected`, `explanation_it`, `type` ∈ grammar | vocab |
preposition | word_order | false_friend | other), `reply`, `new_vocab[]` (`term`, `translation_it`, `example`), `follow_up`.

### 7.2 Modalità (`modes.py`)
- **conversation**: tutor di inglese per un italiano adulto al livello CEFR scelto. Regole chiave: correggere solo errori
  reali; **l'input è una trascrizione automatica** (non correggere punteggiatura/maiuscole, ignorare errori di riconoscimento);
  se l'allievo parla italiano o chiede «come si dice» non è un errore: dare la frase inglese e chiedere di ripeterla; restare
  nel ruolo di tutor; `corrected_sentence` deve applicare tutte le correzioni; la risposta (parlata) è di 1-3 frasi, senza
  elenchi/markdown e senza ripetere le spiegazioni, che sono a schermo; spiegazioni in italiano; max 2 vocaboli nuovi.
- **scenario**: come conversation + `SCENARIO_EXTRA`. *Preparazione*: 4-6 frasi utili in `new_vocab` (`term` = frase inglese,
  `translation_it`, `example` = alternativa/risposta probabile) e una `reply` che presenta la situazione e propone il gioco di
  ruolo. *Gioco di ruolo*: il tutor recita l'altra persona (es. receptionist), risposte brevi, corregge gli errori. `max_tokens`
  = 900 in questa modalità.
- **translate**: traduce IT↔EN fedelmente in `reply`; `follow_up` = al massimo una nota in italiano.
- **Persona** («Alex, un tutor AI che gira in locale») aggiunta solo da `app_system_prompt`; `system_prompt` (usato dal
  benchmark) non la contiene, così la cache del benchmark non si invalida per una questione cosmetica.

### 7.3 Regola d'oro quando si tocca un prompt
Qualsiasi modifica a `CONVERSATION`/`SCHEMA` cambia l'impronta (hash) dei risultati del benchmark: i vecchi risultati vengono
rieseguiti e il report segnala «⚠ risultati con prompt diverso». Dopo ogni modifica rilancia `llm_bench` (set base + `cases_hard.json`).

## 8. Configurazione (variabili d'ambiente / `.env`)

| Variabile | Default | Significato |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Endpoint OpenAI-compatible (Ollama; Splash: `http://127.0.0.1:8000/v1`) |
| `LLM_MODEL` | `gemma4:26b` | Nome del modello (Splash: `mlx-community/Qwen3.6-35B-A3B-4bit`) |
| `LLM_API_KEY` | `local` | Ignorata dai server locali |
| `LLM_TEMPERATURE` | `0.4` | |
| `LLM_MAX_TOKENS` | `700` | Tetto di generazione (scenario: 900) |
| `LLM_JSON_MODE` | `1` | `response_format: json_object`; metti `0` con Splash o se il server lo rifiuta |
| `LLM_EXTRA_BODY` | `{"reasoning_effort":"none"}` | Campi extra del payload. **Spegne il thinking** (vedi §10.2); `{}` lo lascia acceso |
| `STT_BACKEND` | `mlx` | `mlx` (in-process) o `openai` |
| `STT_MODEL` | `mlx-community/whisper-large-v3-turbo` | Backend `mlx` |
| `STT_BASE_URL`, `STT_API_KEY`, `STT_API_MODEL` | — / `local` / `whisper-1` | Backend `openai` |
| `STT_INITIAL_PROMPT` | vuoto | Vocabolario di contesto per Whisper (es. termini tecnici) |
| `AUDIO_MIN_SECONDS`, `AUDIO_MIN_RMS` | `0.4`, `0.004` | Filtro anti-silenzio prima di Whisper |
| `TTS_BASE_URL` | vuoto | Es. `http://localhost:5050/v1`. Vuoto = nessun audio |
| `TTS_MODEL`, `TTS_VOICE_EN`, `TTS_VOICE_IT`, `TTS_FORMAT` | `tts-1`, `alloy`, `alloy`, `mp3` | Il servizio mappa le voci OpenAI su voci macOS e accetta `language` |
| `DB_PATH` | `data/tutor.db` | |
| `HISTORY_TURNS` | `6` | Turni passati all'LLM |

## 9. Frontend

- **Layout**: barra laterale a sinistra con le opzioni (modalità, livello o lingua, microfono, solo ascolto, nuova sessione) e a destra la chat
  (conversazione dall'alto verso il basso con scorrimento automatico, compositore con «● Parla» e campo di testo in basso). Sotto gli 820 px la
  barra diventa un pannello a scomparsa (☰). Chiaro/scuro automatico (`prefers-color-scheme`). Solo CSS puro, nessuna libreria di UI.
- **Stato** (React hooks): sessione (UUID, «Nuova sessione» lo rigenera), modalità, livello, impostazioni audio, turni, errori.
  Le callback asincrone (fine registrazione, fine riproduzione) leggono le impostazioni correnti da un `ref` (`cfg`), per evitare
  closure obsolete.
- **Registrazione**: `getUserMedia` (echo cancellation + noise suppression) → `MediaRecorder` (webm/opus; mp4 su Safari — il
  backend decodifica da contenuto, non dall'estensione) → `POST /api/turn`. Il microfono richiede `localhost` o HTTPS.
- **VAD** (`vad.js`): rilevatore a energia, senza dipendenze né modelli. I primi 400 ms calibrano il rumore di fondo; «voce» =
  RMS > max(0,015; 3 × rumore). Si ferma dopo `pausa` secondi di silenzio *dopo* aver sentito voce, o dopo 10 s senza voce,
  o dopo 90 s. Pausa selezionabile (1,5 / 2,5 / 4 s; 4 s per chi parla lentamente). Verificato in simulazione (tempi di stop,
  pause a metà frase più corte della soglia, rumore costante); **non ancora collaudato con un microfono reale**.
  Limite noto: una pausa di esitazione più lunga della soglia taglia la frase.
- **Conversazione continua**: a fine riproduzione del tutor riparte la registrazione; un errore o «Nuova sessione» la interrompe.
- **Aiuti per l'ascolto**: «Ascolta di nuovo», «Traduci» (`/api/translate`), «Solo ascolto» (testo nascosto finché non si clicca),
  🔊 per ogni frase suggerita nello scenario (`/api/speak`).
- Il frontend mostra la «frase corretta» solo se ci sono correzioni.

## 10. Benchmark e registro delle decisioni

Tutti i dati sono di **un solo parlante** (italiano, accento naturale) su insiemi piccoli: indicano una tendenza, non una verità
statistica. Differenze di 1-2 parole o di 1 caso non sono significative.

### 10.1 STT (progetto `stt-bench`, 40 frasi it/en + 8 coppie di pronuncia)
| Motore | WER italiano | WER inglese (accento italiano) | Note |
|---|---|---|---|
| **Whisper large-v3-turbo (MLX)** | **≈ 5,6 %** (≈ 7,3 % su clip < 30 s) | 19,2 % | regge clip di 38 s; RTF 0,07 |
| Gemma 4 E4B (MLX 4 bit) | ≈ 13,2 % (≈ 9,6 % su clip < 30 s) | 22,1 % | **tronca in silenzio oltre 30 s** (it20: 78 % delle parole) |
| `openai-macos-stt-tts` (Apple Speech) | ≈ 15,8 % | — | sbaglia di più i termini tecnici |

_I WER sono stime calcolate dai report su sottoinsiemi di frasi leggermente diversi (si sono escluse le registrazioni difettose): vale l'ordine di grandezza, non la seconda cifra._

Altri risultati: Gemma E4B non è un valutatore di pronuncia (chiesto quali parole erano sbagliate: **0/8** distinzioni corrette,
falsi allarmi su tutte le take corrette); la traduzione EN→IT con Gemma E4B è inaffidabile; i modelli «normalizzano» spesso la
parola attesa invece di quella pronunciata (≈ metà dei casi) — nessun vantaggio netto di Gemma. **Decisione**: Whisper turbo.
Whisper su silenzio/clip brevissime inventa testo → filtro anti-silenzio (§4).

### 10.2 LLM (`llm_bench`, 28 casi base + 20 difficili)
- **Incidente del thinking**: il primo giro dava 29 % di JSON validi: 21 risposte su 28 troncate esattamente a `max_tokens`
  (900) perché il ragionamento nascosto consumava il budget. Rimedio: `reasoning_effort: "none"` (vale per Ollama `/v1` e
  Splash; `think:false` viene ignorato su `/v1`). Dopo: 100 % valide, 0 troncate.
- Risultati con thinking spento (set base 28 casi): **Gemma 4 26B-A4B** 20/20 errori corretti, 0/8 falsi allarmi, **2,3-2,5 s**,
  88-92 tok/s; **Qwen3.6-35B-A3B** (Splash) 19/20 (incoerenza tra `corrected_sentence` e correzioni su un caso), 0/8,
  **1,1-1,2 s**, ≈ 180 tok/s; **Qwen3.8-27B** 20/20, 4,5 s, 54 tok/s, risposte verbose che ripetono le correzioni.
- Set difficile, primo giro (Gemma e Qwen3.6, prompt precedente): 10/10 errori e 6/6 controlli per entrambi; letti a mano: Gemma interpreta meglio il contesto con trascrizioni imperfette,
  Qwen3.6 si fa deviare di più e ha qualche scivolone in italiano. Caso `a01` (vera trascrizione sbagliata di Whisper):
  dopo le regole aggiunte al prompt Gemma non inserisce più gli errori di riconoscimento tra le correzioni, ma risponde ancora «German» per «Gemma»: unico fallimento (16/17) con i punteggi ricalcolati.
- **Decisione**: Gemma 4 26B-A4B (Ollama) come predefinito per affidabilità con trascrizioni imperfette; Qwen3.6-35B-A3B su
  Splash come alternativa più veloce (cambia solo `LLM_BASE_URL`/`LLM_MODEL`). Splash: motori MoE possono dare output diversi tra
  run a temperatura 0; serve un modello alla volta in memoria (36 GB).

## 11. Strumenti di test

- **`llm_bench`** (dalla cartella, con il venv del backend): `python run_llm_bench.py --models <nome>` (set base),
  `--cases cases_hard.json` (set difficile, risultati in `results/cases_hard/`). Il report include **tutti** i modelli con
  risultati; `--models` decide solo cosa eseguire. I risultati sono salvati con un'impronta (prompt + parametri + testo del caso):
  cambiando prompt o parametri si rieseguono da soli; il punteggio si ricalcola dal testo salvato, quindi modificare
  `scoring.py` non richiede nuove chiamate.
- **Aggiungere un caso**: in `cases*.json` un oggetto con `id`, `text`, `error` e `must_have_any`/`must_not` (correzione attesa
  nella frase corretta) oppure `checks` (più controlli indipendenti per frasi con più errori); `asr_noise` +
  `forbidden_originals` + `reply_must_not` per le trascrizioni sbagliate; `manual: true` per i casi da leggere a mano.
  Semantica del punteggio: «corretto» = nessuna correzione mostrata (come nell'app).
- **`stt-bench`** (progetto separato): `record.py` (registra le frasi dal microfono) e `run_bench.py` (WER/CER per categoria,
  clip lunghe, test di pronuncia). Ogni risultato salvato porta l'impronta dell'audio e si rifà se il file cambia.
- Stato dei test automatici: nessuna suite unitaria formale. Parser JSON, memoria, prompt, punteggio, filtro anti-silenzio e logica
  del VAD sono stati verificati con prove mirate; backend completo e frontend sono stati collaudati a mano dal committente (il
  frontend nelle ultime versioni — scenari, VAD — è stato scritto ma provato in browser solo parzialmente).

## 12. Troubleshooting

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| Un turno molto più lento degli altri (es. LLM 6-7 s con pochi token) | Ollama ha scaricato il modello dopo l'inattività (default 5 min) | `ollama ps` (colonna UNTIL); `OLLAMA_KEEP_ALIVE=-1` e riavviare Ollama |
| «Il modello non ha prodotto il JSON atteso» / risposta troncata | Thinking attivo | Controlla `LLM_EXTRA_BODY` (default `reasoning_effort:none`) |
| Errore 502 «LLM non raggiungibile» | Server spento o URL sbagliato | Avviare Ollama/Splash; verificare `LLM_BASE_URL` |
| 400 «non ho sentito nulla» | Audio troppo breve/silenzioso | Parlare più vicino al microfono; abbassare `AUDIO_MIN_RMS` se il microfono è debole |
| La registrazione si ferma a metà frase | Pausa più lunga della soglia del VAD | Selezionare «4 s» o disattivare lo stop automatico |
| Nessuna voce del tutor | `TTS_BASE_URL` vuoto o servizio spento | Impostare l'URL (porta 5050); nel `.env` del servizio `USE_HTTP=True` per http |
| Voce inglese con pronuncia italiana | Il TTS usa la voce sbagliata | Verificare il parametro `language` e le voci inglesi installate in macOS |
| «ffmpeg non trovato» | Dipendenza di sistema | `brew install ffmpeg` |
| Dopo un aggiornamento l'interfaccia non cambia | Il backend (porta 8010) serve una vecchia `frontend/dist` | `./run.sh` (ricompila da solo) oppure `cd frontend && npm run build`; la «build …» in fondo alla barra laterale dice quale versione gira |
| Microfono negato | Permessi del browser/OS | Consentire il microfono (serve `localhost` o HTTPS) |
| Memoria insufficiente / lentezza generale | Più modelli caricati insieme (36 GB) | Un solo LLM alla volta; limitare il contesto (`--max-context` in Splash) |

## 13. Distribuzione

**A) Sviluppo** (oggi): backend con `uvicorn --reload` (porta 8010) + `npm run dev` (Vite su 5173, proxy `/api`).

**B) Un solo processo** (consigliato per l'uso quotidiano): `./run.sh`. Compila il frontend se manca la build o se i sorgenti sono
più recenti (`npm run build`) e il backend lo serve da `/`; Node non serve più a runtime. Si apre `http://127.0.0.1:8010`.

**C) Docker — analisi.** Su Mac un container è una VM Linux **senza accesso a Metal**: Whisper-MLX, Ollama/Splash e il TTS basato su
`say` non possono girare dentro. Dentro il container può stare solo l'orchestrator con il frontend; STT, LLM e TTS restano
sull'host e si raggiungono via `host.docker.internal`. Poiché lo STT oggi è in-process (MLX), serve `STT_BACKEND=openai` verso un
server STT sull'host: **oggi non ce n'è uno con Whisper su Metal** (il servizio `openai-macos-stt-tts` usa Apple Speech, risultato
peggiore nei test). Conclusione: su Mac Docker aggiunge complessità senza benefici. Ha senso su **Linux con GPU NVIDIA**
(faster-whisper + Ollama in container) o per un server domestico condiviso. `deploy/Dockerfile` e `deploy/docker-compose.yml`
sono bozze **non testate**: orchestrator + UI, `STT_BACKEND=openai`, volume per il database, porta solo su localhost.

**D) App desktop (Tauri) — analisi.** Percorso più sensato su Mac: Tauri come *guscio* (finestra WKWebView su
`http://127.0.0.1:8010`) che avvia/ferma come processo figlio `run.sh` (o l'`uvicorn` del venv). Non conviene impacchettare il
backend con PyInstaller: MLX porta librerie native e file Metal difficili da includere. Punti di attenzione: permesso microfono
(`NSMicrophoneUsageDescription` nell'Info.plist e relativa entitlement; il supporto di `getUserMedia` nella WKWebView va
verificato sulla versione di macOS in uso), Ollama/Splash e il TTS restano installazioni separate (da avviare o da richiedere
all'utente), firma e notarizzazione per distribuire l'app ad altri. Alternativa a costo quasi zero: aprire la pagina in un browser e
usare «Installa come app/aggiungi al Dock» (comportamento da verificare), più un LaunchAgent `launchd` che esegue `run.sh` al login.

## 14. Sicurezza e privacy
- Il server ascolta su `127.0.0.1`: non esporlo in rete. Non c'è autenticazione, quindi chiunque raggiunga la porta può usare
  LLM e leggere `/api/vocab`/`/api/mistakes`. CORS consente solo l'origine Vite di sviluppo.
- Audio e testo restano locali; i file temporanei (webm/wav) sono eliminati dopo la trascrizione. Il database contiene le frasi
  dell'allievo: tratta `data/` come dati personali.
- I modelli si scaricano da Hugging Face/Ollama la prima volta (unica attività di rete).

## 15. Limiti noti e roadmap (in ordine di valore)

1. **Valutazione della pronuncia**: oggi assente. Gemma non è affidabile (0/8). Strada: modello fonemico (es. wav2vec2 per
   fonemi) + forced alignment sul testo atteso, e LLM solo per spiegare. Modalità **shadowing**: il tutor dice una frase,
   l'allievo la ripete, l'app confronta trascrizione e frase attesa.
2. **Streaming** (WebSocket): far partire il TTS sulla `reply` mentre l'LLM genera ancora le correzioni; con ≈ 2,6 s di latenza
   attuale è secondario.
3. **Ripasso e memoria**: usare `mistakes` e `vocab` (ripetizione dilazionata, errori ricorrenti nel prompt, livello adattivo).
4. **VAD neurale** (Silero) se il rumore ambientale mette in difficoltà quello a energia.
5. **Scenari predefiniti** e obiettivi di sessione; riepilogo a fine sessione.
6. **Test automatici**: suite pytest su parser, orchestrator (con provider finti), API (httpx/TestClient) e CI che lanci `llm_bench`.
7. **STT intercambiabile con Whisper su Metal via HTTP**, per sbloccare Docker e l'uso da altri dispositivi.
8. **Altre lingue**: i prompt sono parametrizzabili in `modes.py` (`LANG_NAME`, `CONVERSATION`); servono voci TTS e un set di casi di benchmark.
9. **Estetica**: barra laterale + chat, tema chiaro/scuro automatico, CSS puro; nessun lavoro di design oltre a questo (niente icone dedicate, animazioni o PWA).

## 16. Come estendere

- **Nuova modalità**: aggiungi il prompt in `modes.py` (`system_prompt`, eventualmente `reply_language`); consenti il nome in
  `main.py` (validazione `mode`) e in `orchestrator.py` (storia/`max_tokens`); aggiungi l'opzione in `App.jsx`; scrivi casi nel
  benchmark; rilancia `llm_bench`.
- **Nuovo provider** (STT/LLM/TTS): implementa la stessa interfaccia in `providers/` (`transcribe`, `chat`/`tutor_reply`,
  `speak`) e selezionalo da `config.py`.
- **Nuovo modello LLM**: aggiungi la voce in `llm_bench/models.toml`, esegui il benchmark (con thinking spento), poi imposta
  `LLM_BASE_URL`/`LLM_MODEL`.
- **Nuovo campo nel JSON del tutor**: aggiorna `SCHEMA` in `modes.py`, `schemas.py`, il frontend, `scoring.py` se rilevante, e
  rilancia il benchmark (cambia l'impronta dei risultati).
