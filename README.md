# tutor-local: tutor vocale italiano/inglese, tutto in locale

Whisper (STT) → LLM (tutor) → TTS, orchestrati da un backend FastAPI, con un frontend React minimale.
Il progetto parte volutamente piccolo: un turno = una richiesta HTTP, poi si ottimizza.

```
backend/    FastAPI: orchestrator, provider STT/LLM/TTS, memoria SQLite
frontend/   React (Vite): registra, mostra correzioni e risposta, riproduce l'audio
llm_bench/  benchmark per scegliere il modello LLM sul compito reale del tutor
```

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
Per lo sviluppo con ricarica automatica usa invece i due comandi qui sotto. **Documentazione tecnica completa: `docs/TECHNICAL.md`.**

### Sviluppo

```bash
cp .env.example .env              # imposta LLM_BASE_URL/LLM_MODEL con il vincitore; TTS_BASE_URL=http://localhost:5050/v1 per la voce
cd backend && uvicorn app.main:app --port 8010 --reload
# in un altro terminale:
cd frontend && npm install && npm run dev      # http://localhost:5173
```
Alla prima richiesta vocale Whisper scarica il modello. Se non vedi l'audio della risposta, controlla `TTS_BASE_URL`:
(il tuo `openai-macos-stt-tts` ascolta sulla 5050; l'app gli passa `voice` e `language`, quindi la voce inglese dipende dalle voci di sistema installate e dal mapping in `config.py` del servizio). Senza, l'app risponde solo con il testo (il TTS è facoltativo e non blocca il turno se fallisce).

## Interfaccia

Barra laterale con le opzioni e chat a destra (tema chiaro/scuro automatico; sotto gli 820 px la barra si apre con ☰).

## Audio

- **Stop automatico al silenzio** (VAD a energia, nel browser): la registrazione si ferma dopo una pausa regolabile (1,5 / 2,5 / 4 s).
- **Conversazione continua**: finito il tutor, riparte l'ascolto da solo.
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
4. Il TTS pronuncia `reply`. Errori e vocabolario vengono salvati in `data/tutor.db` (`/api/mistakes`, `/api/vocab`).

Il prompt dice al modello che l'input è una **trascrizione automatica**: non deve correggere punteggiatura o maiuscole
né inseguire errori di riconoscimento. I casi `c07`/`c08` del benchmark verificano proprio questo.

## Limiti noti e prossimi passi

- **Latenza**: oggi una risposta arriva intera. Il passo successivo è lo streaming (WebSocket): far partire il TTS sul
  `reply` mentre il modello genera ancora le correzioni.
- **Pronuncia**: non è valutata. Gemma non l'ha giudicata in modo affidabile nei test; serve un modulo fonemico separato.
- **Clip lunghe**: Whisper le gestisce; i modelli audio-nativi con limite di 30 s no.
- **Memoria**: gli errori sono salvati ma ancora non influenzano le sessioni successive (ripasso, livello adattivo).
- **Thinking**: se il modello ragiona prima di rispondere la latenza esplode; disattivalo con `LLM_EXTRA_BODY` se il server lo permette.
