# tutor-local: local-first Italian↔English voice tutor

Whisper (STT) → LLM (tutor) → TTS, orchestrated by a FastAPI backend, with a React frontend.
The project starts deliberately small: one turn = one HTTP request, then optimise.

> **⚠️ Disclaimer**: tutor-local is an **experimental** project, built with the help of AI tools. The author assumes no responsibility for use of this code.

> **Student?** Read [GUIDA-STUDENTE.md](GUIDA-STUDENTE.md) (Italian): features, usage examples, and study routines.

> **Italiano?** See [README.md](README.md).

```
backend/     FastAPI: orchestrator, STT/LLM/TTS providers, SQLite memory, pytest suite
frontend/    React (Vite): App.jsx (state) + components/ + hooks/ + vad.js
llm_bench/   benchmark to pick the LLM on the real tutor task
docs/        TECHNICAL.md (architecture, contracts, decisions — Italian)
```

Frontend layout: `App.jsx` owns state and API/recording flows; UI pieces live under `frontend/src/components/` (Sidebar, TopBar, Composer, TurnExchange, HelpPanel, ReviewPanel, PronunciationFeedback). Full technical detail: [`docs/TECHNICAL.md`](docs/TECHNICAL.md) §9.

## 1. Choose the model (llm_bench)

```bash
brew install ffmpeg
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
ollama pull gemma4:26b            # check tags with `ollama list`; see llm_bench/models.toml
cd ../llm_bench
python run_llm_bench.py --models gemma4_26b_a4b      # then other models, one at a time
```

**Thinking off**: the runner sends `reasoning_effort: "none"` (works for Ollama `/v1` and Splash). If thinking stays on, reasoning
consumes `max_tokens` and replies arrive truncated or empty — the report shows this in the «Troncati» and «Con thinking» columns.
With 36 GB keep **one** model in memory at a time (stop Ollama with `ollama stop <model>` before starting `splash serve`).
Splash serves MLX checkpoints (e.g. `splash serve --model mlx-community/Qwen3.6-35B-A3B-4bit --max-context 32K`); IDs are in `models.toml`.

The report (`llm_bench/results/report.md`) includes **all** models that already have saved results, even if you run only one
(`--models` only selects what to execute). After a saturated first pass (everyone near 100%), use the harder set:
`python run_llm_bench.py --cases cases_hard.json --models <model>` (multiple errors, subtle errors, correct controls,
and four “read by hand” cases; results in `results/cases_hard/`).

The report scores 28 sentences: valid JSON, errors fixed well, false alarms on correct sentences (including transcripts without
capitalisation/punctuation), explanations in Italian, TTS-friendly replies, latency and tok/s. Also read the full examples:
Italian quality is not a single number.

## 2. Start the tutor (one command)

```bash
./run.sh      # builds the frontend the first time and serves everything at http://127.0.0.1:8010
```

For development with hot reload, use the two commands below. **Full technical docs: [`docs/TECHNICAL.md`](docs/TECHNICAL.md).**

### Development

```bash
cp .env.example .env              # set LLM_BASE_URL/LLM_MODEL to the winner and TTS as below
cd backend && uvicorn app.main:app --port 8010 --reload
# in another terminal:
cd frontend && npm install && npm run dev      # http://localhost:5173
```

On the first voice request Whisper downloads the model. TTS uses the local `openai-macos-stt-tts` service (macOS `say` system voices), started separately on port 5050. In that service’s `.env` enable HTTP (`USE_HTTP=True`); in tutor-local set the macOS voices mapped by the service:

```dotenv
TTS_BASE_URL=http://127.0.0.1:5050/v1
TTS_API_KEY=local
TTS_MODEL=tts-1
TTS_VOICE_IT=alloy
TTS_VOICE_EN=ash
TTS_FORMAT=mp3
```

`TTS_VOICE_IT` and `TTS_VOICE_EN` are macOS voice names mapped by the service, not audio files — make sure the matching voices are installed. The backend sends language on every synthesis, including English quotes inside Italian explanations. MP3 needs `ffmpeg` (already required by the backend). Without `TTS_BASE_URL` the app replies with text only; if TTS fails the turn is not aborted.

## Interface

Sidebar with options and chat on the right (automatic light/dark theme; under 820 px the sidebar opens with ☰).

## Audio

- **Auto-stop on silence** (energy VAD in the browser): recording stops after an adjustable pause (1.5 / 2.5 / 4 s).
- **Continuous conversation**: when the tutor finishes speaking, listening starts again on its own.
- **Spoken explanations**: enable «Leggi le spiegazioni in italiano» in the listening options to hear them after the tutor reply.
- **English speed**: choose 0.8×–1.2× in the left bar; Italian synthesis stays at normal speed.
- **Contextual help**: open «Chiedi in italiano» from the top bar to type or speak a question. The tutor answers in Italian in a separate side panel, using the dialogue as context without interrupting practice. English phrases in the answer use the English voice; explanations use the Italian voice.
- **Suggested reply**: the tutor proposes a possible answer to its last question so you know what to say next. You can listen and practise it; on corrected sentences you can also listen and repeat the fix.
- Very short or silent audio never reaches Whisper (avoids invented phrases like «Thank you.»).

## Modes

- **Conversation**: English dialogue with corrections in Italian.
- **Scenario**: describe a situation in Italian («Help me check in at a hotel for a room»); the tutor gives 4–6 useful phrases (with 🔊 and translation), then role-plays the other person (e.g. receptionist) and corrects you. «↺ Nuova sessione» to change scenario.
- **Translation**: IT↔EN. In every mode: «Listen again», «Translate», and «Listen only».

## How a turn works

1. `POST /api/turn` (browser audio or text, mode, level, spoken language).
2. ffmpeg converts to 16 kHz; Whisper transcribes (`stt` in timings).
3. The LLM receives the mode prompt (`app/modes.py`) + recent turns and returns JSON
   (`is_correct`, `corrected_sentence`, `corrections`, `reply`, `new_vocab`, `follow_up`). If JSON is invalid it retries once.
4. TTS speaks `reply`. In conversation and role-play the LLM also provides `suggested_reply`, a sample learner answer to the next question; the UI lets you listen and score the repetition with the phonetic engine. Errors and vocabulary are stored in `data/tutor.db` (`/api/mistakes`, `/api/vocab`) and feed the review queue.

The prompt tells the model that the input is an **automatic transcript**: it must not “fix” punctuation/capitalisation or chase recognition errors. Benchmark cases `c07`/`c08` check exactly this.

## Review and session summary

- **🔁 Ripasso** (top bar): queue of due errors and vocab, with four grades (Didn’t remember / Hard / Good / Easy). Scheduling is a simplified SM-2: a just-failed item returns in about 10 minutes; positive grades stretch the interval. The badge shows how many items are ready.
- After a reply you can **listen to the correct pronunciation** and **repeat it**: the phonetic engine (Wav2Vec2 XLSR-53 + `phonemizer`) compares individual sounds and shows a 0–100 score, estimated phonemes, and expected/heard IPA. It does not score accent or prosody.
- Due items are also injected into the conversation prompt (at most 3 errors and 3 vocab items), only when a natural opportunity arises — the tutor does not turn the dialogue into a quiz. The benchmark does not receive this block.
- The same panel shows the **session summary**: turns, deduplicated corrections and vocab, read from saved turns.

## Tests

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check app tests
```

The suite uses a temporary database and fake providers: it does not touch `data/tutor.db` or real services.

## Known limits and next steps

- **Latency**: today a full reply arrives at once. Next step is streaming (WebSocket): start TTS on `reply` while the model is still generating corrections.
- **Pronunciation**: scored at phoneme level (0–100 and IPA), not accent or prosody. The benchmark is a single Italian-accented speaker; absolute scores are not calibrated to human judgement. Italian is out of scope for v1.
- **Long clips**: Whisper handles them; native audio models with a 30 s limit do not.
- **Review**: queue and prompt injection are live; adaptive level and historical stats are still missing.
- **Thinking**: if the model reasons before answering, latency explodes; turn it off with `LLM_EXTRA_BODY` when the server allows it.
