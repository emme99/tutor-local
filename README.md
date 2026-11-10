# tutor-local: tutor vocale italiano/inglese, tutto in locale

Whisper (STT) → LLM (tutor) → TTS, orchestrati da un backend FastAPI, con un frontend React.
Il progetto parte volutamente piccolo: un turno = una richiesta HTTP, poi si ottimizza.

> **⚠️ Disclaimer**: tutor-local è un progetto **sperimentale**, realizzato con l'ausilio di strumenti di intelligenza artificiale. L'autore non si assume alcuna responsabilità per l'utilizzo di questo codice.

> **Sei uno studente?** Leggi [GUIDA-STUDENTE.md](GUIDA-STUDENTE.md): funzionalità, esempi d'uso e routine di studio.

> **English?** See [README-EN.md](README-EN.md).

```
backend/     FastAPI: orchestrator, provider STT/LLM/TTS, memoria SQLite, suite pytest
frontend/    React (Vite): App.jsx (stato) + components/ + hooks/ + vad.js
llm_bench/   benchmark per scegliere il modello LLM sul compito reale del tutor
docs/        TECHNICAL.md (architettura, contratti, decisioni)
```

Il frontend è organizzato così: `App.jsx` tiene stato e chiamate API; i pezzi di UI vivono in `frontend/src/components/` (Sidebar, TopBar, Composer, TurnExchange, HelpPanel, ReviewPanel, PronunciationFeedback). Dettagli in [`docs/TECHNICAL.md`](docs/TECHNICAL.md) §9.

## 1. Scegli il modello (llm_bench)

```bash
brew install ffmpeg
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
ollama pull gemma4:26b            # verifica i tag con `ollama list`; vedi llm_bench/models.toml
cd ../llm_bench
python run_llm_bench.py --models gemma4_26b_a4b      # poi gli altri, uno alla volta
```

**Thinking spento**: il runner invia `reasoning_effort: "none"` (vale per Ollama `/v1` e per Splash). Se lo lasci acceso il ragionamento
consuma `max_tokens` e le risposte arrivano troncate o vuote: nel report lo vedi dalle colonne «Troncati» e «Con thinking».
Con 36 GB tieni in memoria **un solo** modello alla volta (ferma Ollama con `ollama stop <modello>` prima di avviare `splash serve`).
Splash serve checkpoint MLX (es. `splash serve --model mlx-community/Qwen3.6-35B-A3B-4bit --max-context 32K`); gli ID sono in `models.toml`.

Il report (`llm_bench/results/report.md`) include **tutti** i modelli che hanno già risultati salvati, anche se ne esegui uno solo
(`--models` sceglie solo cosa eseguire). Dopo un primo giro saturo (tutti vicini al 100%), usa il set più difficile:
`python run_llm_bench.py --cases cases_hard.json --models <modello>` (errori multipli, errori sottili, controlli corretti,
e quattro casi «da leggere a mano»; risultati in `results/cases_hard/`).

Il report misura su 28 frasi: JSON valido, errori corretti bene, falsi allarmi su
frasi corrette (incluse trascrizioni senza maiuscole/punteggiatura), spiegazioni in italiano, risposte adatte al TTS,
latenza e tok/s. Leggi anche gli esempi completi: la qualità dell'italiano non si misura con un numero.

## 2. Avvia il tutor (un solo comando)

```bash
./run.sh      # compila il frontend la prima volta e serve tutto su http://127.0.0.1:8010
```

Per lo sviluppo con ricarica automatica usa invece i due comandi qui sotto. **Documentazione tecnica completa: [`docs/TECHNICAL.md`](docs/TECHNICAL.md).**

### Sviluppo

```bash
cp .env.example .env              # imposta LLM_BASE_URL/LLM_MODEL con il vincitore e la configurazione TTS qui sotto
cd backend && uvicorn app.main:app --port 8010 --reload
# in un altro terminale:
cd frontend && npm install && npm run dev      # http://localhost:5173
```

Alla prima richiesta vocale Whisper scarica il modello. Il TTS usa il servizio locale `openai-macos-stt-tts`, basato sulle voci di sistema di macOS tramite `say`, avviato separatamente sulla porta 5050. Nel `.env` del servizio abilita HTTP (`USE_HTTP=True`); in tutor-local imposta le voci macOS configurate nel servizio:

```dotenv
TTS_BASE_URL=http://127.0.0.1:5050/v1
TTS_API_KEY=local
TTS_MODEL=tts-1
TTS_VOICE_IT=alloy
TTS_VOICE_EN=ash
TTS_FORMAT=mp3
```

`TTS_VOICE_IT` e `TTS_VOICE_EN` sono i nomi delle voci macOS mappati dal servizio, non file audio: verifica che le voci corrispondenti siano installate. Il backend invia la lingua a ogni sintesi, incluse le citazioni inglesi nelle spiegazioni italiane. MP3 richiede `ffmpeg`, già necessario al backend. Senza `TTS_BASE_URL` l'app risponde solo con il testo; se il TTS fallisce il turno non viene interrotto.

## Interfaccia

Barra laterale con le opzioni e chat a destra (tema chiaro/scuro automatico; sotto gli 820 px la barra si apre con ☰).

## Audio

- **Stop automatico al silenzio** (VAD a energia, nel browser): la registrazione si ferma dopo una pausa regolabile (1,5 / 2,5 / 4 s).
- **Conversazione continua**: finito il tutor, riparte l'ascolto da solo.
- **Spiegazioni vocali**: attiva «Leggi le spiegazioni in italiano» nelle opzioni di ascolto per sentirle dopo la risposta del tutor.
- **Velocità inglese**: scegli nella barra sinistra una velocità da 0,8× a 1,2×; le sintesi italiane restano a velocità normale.
- **Aiuto contestuale**: apri «Chiedi in italiano» dalla barra superiore per scrivere o pronunciare una domanda. Il tutor risponde in italiano in un pannello laterale separato, usando il dialogo come contesto senza interrompere né modificare la pratica. Le frasi e le parole inglesi nella risposta vengono pronunciate con la voce inglese, le spiegazioni con quella italiana.
- **Risposta suggerita**: il tutor propone una possibile risposta alla sua ultima domanda, così sai cosa dire per continuare il dialogo. Puoi ascoltarla e provarla; sulle frasi errate puoi anche ascoltare e ripetere la correzione.
- Audio troppo breve o silenzioso non arriva a Whisper (evita le frasi inventate tipo «Thank you.»).

## Modalità

- **Conversazione**: dialogo in inglese con correzioni in italiano.
- **Scenario**: descrivi in italiano una situazione («Aiutami a presentarmi in albergo per avere una camera») e il tutor ti dà
  4-6 frasi da dire (con 🔊 per ascoltarle e la traduzione), poi fai un gioco di ruolo in cui lui interpreta l'altra persona
  (il receptionist) e ti corregge. «↺ Nuova sessione» per cambiare scenario.
- **Traduzione**: IT↔EN. In ogni modalità: «Ascolta di nuovo», «Traduci» e «Solo ascolto».

## Come funziona un turno

1. `POST /api/turn` (audio del browser o testo, modalità, livello, lingua parlata).
2. ffmpeg converte a 16 kHz, Whisper trascrive (`stt` nei tempi).
3. L'LLM riceve il prompt della modalità (`app/modes.py`) + gli ultimi turni e restituisce un JSON
   (`is_correct`, `corrected_sentence`, `corrections`, `reply`, `new_vocab`, `follow_up`). Se il JSON non è valido riprova una volta.
4. Il TTS pronuncia `reply`. In conversazione e gioco di ruolo l'LLM fornisce anche `suggested_reply`, un esempio di risposta dell'allievo alla domanda successiva; la UI consente di ascoltarla e valutarne la ripetizione con il motore fonetico. Errori e vocabolario vengono salvati in `data/tutor.db` (`/api/mistakes`, `/api/vocab`) e alimentano la coda di ripasso.

Il prompt dice al modello che l'input è una **trascrizione automatica**: non deve correggere punteggiatura o maiuscole
né inseguire errori di riconoscimento. I casi `c07`/`c08` del benchmark verificano proprio questo.

## Ripasso e riepilogo

- **🔁 Ripasso** (barra superiore): coda degli errori e dei vocaboli in scadenza, con quattro voti (Non ricordavo / Difficile /
  Bene / Facile). La programmazione è una versione semplificata di SM-2: un errore appena sbagliato torna dopo circa 10 minuti,
  mentre i voti positivi aumentano l'intervallo. Il badge mostra quanti elementi sono pronti.
- Dopo la risposta puoi **ascoltare la pronuncia corretta** e **ripeterla**: il motore fonetico (Wav2Vec2 XLSR-53 + `phonemizer`)
  confronta i singoli suoni e mostra uno score 0–100, i fonemi stimati e le sequenze IPA attesa/pronunciata. Non valuta accento
  né prosodia.
- Gli elementi scaduti vengono richiamati anche nel prompt della conversazione (al massimo 3 errori e 3 vocaboli), solo quando
  l'occasione è naturale: il tutor non trasforma il dialogo in un test. Il benchmark non riceve questo blocco.
- Nello stesso pannello compare il **riepilogo della sessione**: turni, correzioni e vocaboli deduplicati, letto dai turni salvati.

## Test

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check app tests
```

La suite usa un database temporaneo e provider finti: non tocca `data/tutor.db` né i servizi reali.

## Limiti noti e prossimi passi

- **Latenza**: oggi una risposta arriva intera. Il passo successivo è lo streaming (WebSocket): far partire il TTS sul
  `reply` mentre il modello genera ancora le correzioni.
- **Pronuncia**: è valutata a livello di fonemi (score 0–100 e IPA), non di accento o prosodia. Il benchmark è su un solo
  parlante con accento italiano: lo score assoluto non è calibrato come un giudizio umano. L'italiano è fuori v1.
- **Clip lunghe**: Whisper le gestisce; i modelli audio-nativi con limite di 30 s no.
- **Ripasso**: la coda e l'iniezione nel prompt sono attive; mancano livello adattivo e statistiche storiche.
- **Thinking**: se il modello ragiona prima di rispondere la latenza esplode; disattivalo con `LLM_EXTRA_BODY` se il server lo permette.
