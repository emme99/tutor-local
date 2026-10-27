import { useEffect, useRef, useState } from "react";
import { startVAD } from "./vad.js";

let nextId = 1;

export default function App() {
  const [session, setSession] = useState(() => crypto.randomUUID());
  const [mode, setMode] = useState("conversation");
  const [level, setLevel] = useState("B1");
  const [lang, setLang] = useState("en");
  const [autoStop, setAutoStop] = useState(true);
  const [pauseMs, setPauseMs] = useState(2500);
  const [continuous, setContinuous] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [turns, setTurns] = useState([]);
  const [error, setError] = useState("");
  const [hideText, setHideText] = useState(false);
  const [revealed, setRevealed] = useState({});
  const [translations, setTranslations] = useState({});
  const [sideOpen, setSideOpen] = useState(false);

  const recorder = useRef(null);
  const chunks = useRef([]);
  const player = useRef(null);
  const stopVad = useRef(null);
  const listRef = useRef(null);
  // Le callback asincrone (fine registrazione, fine audio) leggono sempre le impostazioni correnti da qui.
  const cfg = useRef({});
  cfg.current = { session, mode, level, lang, autoStop, pauseMs, continuous };

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  function play(t, onEnd) {
    if (!t.audio_b64) {
      onEnd?.();
      return;
    }
    player.current?.pause();
    const a = new Audio(`data:${t.audio_mime};base64,${t.audio_b64}`);
    player.current = a;
    if (onEnd) a.onended = onEnd;
    a.play().catch(() => onEnd?.());
  }

  async function submit(form) {
    const c = cfg.current;
    setBusy(true);
    setError("");
    form.append("session_id", c.session);
    form.append("mode", c.mode);
    form.append("level", c.level);
    form.append("spoken_lang", c.lang);
    try {
      const r = await fetch("/api/turn", { method: "POST", body: form });
      if (!r.ok) {
        let msg = r.statusText;
        try { msg = (await r.json()).detail || msg; } catch { /* corpo non JSON */ }
        throw new Error(msg);
      }
      const data = await r.json();
      data.id = nextId++;
      setTurns((t) => [...t, data]);
      // In "conversazione continua" quando il tutor ha finito di parlare si riascolta da soli.
      play(data, cfg.current.continuous ? () => cfg.current.continuous && startRecording() : undefined);
    } catch (e) {
      setError(String(e.message || e));
      setContinuous(false); // un errore interrompe il ciclo automatico
    } finally {
      setBusy(false);
    }
  }

  async function startRecording() {
    if (recorder.current?.state === "recording") return;
    player.current?.pause(); // niente voce del tutor nel microfono
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      mr.onstop = () => {
        stopVad.current?.();
        stopVad.current = null;
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        setMicLevel(0);
        const form = new FormData();
        form.append("audio", new Blob(chunks.current, { type: mr.mimeType }), "turn.webm");
        submit(form);
      };
      mr.start();
      recorder.current = mr;
      setRecording(true);
      if (cfg.current.autoStop) {
        stopVad.current = startVAD(stream, {
          silenceMs: cfg.current.pauseMs,
          onLevel: setMicLevel,
          onStop: () => mr.state === "recording" && mr.stop(),
        });
      }
    } catch (e) {
      setError("Microfono non disponibile: " + e.message);
      setContinuous(false);
    }
  }

  function toggleRecording() {
    if (recording) recorder.current?.stop();
    else startRecording();
  }

  async function speakPhrase(phrase) {
    try {
      const r = await fetch("/api/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: phrase, lang: "en" }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || r.statusText);
      play({ audio_b64: d.audio_b64, audio_mime: d.audio_mime });
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  function newSession() {
    setContinuous(false);
    setSession(crypto.randomUUID());
    setTurns([]);
    setTranslations({});
    setRevealed({});
    setError("");
  }

  async function translate(t) {
    const joined = [t.tutor.reply, t.tutor.follow_up].filter(Boolean).join(" ");
    setTranslations((m) => ({ ...m, [t.id]: "…" }));
    try {
      const r = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: joined, target: "it" }),
      });
      const d = await r.json();
      setTranslations((m) => ({ ...m, [t.id]: r.ok ? d.translation : d.detail || "errore" }));
    } catch (e) {
      setTranslations((m) => ({ ...m, [t.id]: "errore: " + e.message }));
    }
  }

  function sendText(e) {
    e.preventDefault();
    if (!text.trim()) return;
    const form = new FormData();
    form.append("text", text);
    setText("");
    submit(form);
  }

  const modeLabel = { conversation: "Conversazione", scenario: "Scenario", translate: "Traduzione" }[mode];
  const hints = {
    conversation: "Premi ● Parla e dì qualcosa in inglese, per esempio «My name is…». Il tutor ti risponde e ti corregge.",
    scenario: "Descrivi in italiano una situazione, per esempio «Aiutami a presentarmi in albergo per avere una camera»: riceverai le frasi da dire e poi farete un gioco di ruolo.",
    translate: "Parla (o scrivi) nella lingua scelta a sinistra: il tutor traduce e pronuncia la traduzione.",
  };

  return (
    <div className="app">
      <aside className={sideOpen ? "side open" : "side"}>
        <div className="brand">
          <h1>Tutor locale</h1>
          <p className="muted small">Tutto in locale: Whisper, LLM e TTS sul tuo Mac.</p>
        </div>

        <div className="group">
          <h2>Modalità</h2>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="conversation">Conversazione (inglese)</option>
            <option value="scenario">Scenario (frasi + gioco di ruolo)</option>
            <option value="translate">Traduzione</option>
          </select>
          {mode !== "translate" ? (
            <label className="field">Livello
              <select value={level} onChange={(e) => setLevel(e.target.value)}>
                {["A2", "B1", "B2", "C1"].map((l) => <option key={l}>{l}</option>)}
              </select>
            </label>
          ) : (
            <label className="field">Parlo in
              <select value={lang} onChange={(e) => setLang(e.target.value)}>
                <option value="it">Italiano → inglese</option>
                <option value="en">Inglese → italiano</option>
              </select>
            </label>
          )}
        </div>

        <div className="group">
          <h2>Microfono</h2>
          <label className="check">
            <input type="checkbox" checked={autoStop} onChange={(e) => setAutoStop(e.target.checked)} />
            Stop automatico al silenzio
          </label>
          <label className="field">Pausa che mi ferma
            <select value={pauseMs} onChange={(e) => setPauseMs(Number(e.target.value))} disabled={!autoStop}>
              <option value={1500}>1,5 s</option>
              <option value={2500}>2,5 s</option>
              <option value={4000}>4 s (parlo lentamente)</option>
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={continuous} onChange={(e) => setContinuous(e.target.checked)} disabled={!autoStop} />
            Conversazione continua
          </label>
        </div>

        <div className="group">
          <h2>Ascolto</h2>
          <label className="check">
            <input type="checkbox" checked={hideText} onChange={(e) => setHideText(e.target.checked)} />
            Solo ascolto (nascondi il testo del tutor)
          </label>
        </div>

        <button type="button" className="ghost" onClick={() => { newSession(); setSideOpen(false); }}>
          ↺ Nuova sessione
        </button>
        <p className="muted small build">build {typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "dev"}</p>
      </aside>

      {sideOpen && <div className="scrim" onClick={() => setSideOpen(false)} />}

      <main className="chat">
        <header className="topbar">
          <button type="button" className="menu ghost" onClick={() => setSideOpen(true)} aria-label="Opzioni">☰</button>
          <strong>{modeLabel}</strong>
          <span className="muted small">
            {mode === "translate" ? (lang === "it" ? "italiano → inglese" : "inglese → italiano") : `livello ${level}`}
          </span>
        </header>

        <div className="messages" ref={listRef}>
          {turns.length === 0 && <p className="empty">{hints[mode]}</p>}

          {turns.map((t) => {
            const hidden = hideText && !revealed[t.id];
            const reveal = () => hideText && setRevealed((r) => ({ ...r, [t.id]: true }));
            const showFix = t.mode !== "translate" && t.tutor.corrections.length > 0;
            return (
              <div key={t.id} className="exchange">
                <div className="row user">
                  <div className="bubble user">{t.transcript}</div>
                </div>

                <div className="row tutor">
                  <div className="stack">
                    {showFix && (
                      <div className="note">
                        {t.tutor.corrected_sentence && <div className="fix">✎ {t.tutor.corrected_sentence}</div>}
                        {t.tutor.corrections.map((c, j) => (
                          <div key={j} className="corr">
                            <b>{c.original}</b> → <b>{c.corrected}</b>
                            <span> {c.explanation_it}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className={hidden ? "bubble tutor hidden" : "bubble tutor"} onClick={reveal}>
                      {hidden ? "••• ascolta, poi clicca per leggere" : (
                        <>
                          <div>{t.tutor.reply}</div>
                          {t.tutor.follow_up && <div className="follow">{t.tutor.follow_up}</div>}
                        </>
                      )}
                    </div>

                    {translations[t.id] && <div className="translation">🇮🇹 {translations[t.id]}</div>}

                    {t.mode === "scenario" && t.tutor.new_vocab.length > 0 && (
                      <div className="phrases">
                        {t.tutor.new_vocab.map((v) => (
                          <div key={v.term} className="phrase">
                            <button type="button" className="icon" onClick={() => speakPhrase(v.term)} title="Ascolta">🔊</button>
                            <div>
                              <b>{v.term}</b>
                              <div className="muted">{v.translation_it}</div>
                              {v.example && <div className="muted small">{v.example}</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {t.mode !== "scenario" && t.tutor.new_vocab.length > 0 && (
                      <div className="vocab">
                        {t.tutor.new_vocab.map((v) => (
                          <span key={v.term} title={v.example}>{v.term} = {v.translation_it}</span>
                        ))}
                      </div>
                    )}

                    <div className="actions">
                      {t.audio_b64 && <button type="button" className="ghost" onClick={() => play(t)}>🔊 Ascolta di nuovo</button>}
                      <button type="button" className="ghost" onClick={() => translate(t)}>🇮🇹 Traduci</button>
                      <span className="timings">
                        {Object.entries(t.timings).map(([k, v]) => `${k} ${v}${k.includes("tok") ? "" : " s"}`).join(" · ")}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          {busy && (
            <div className="row tutor">
              <div className="bubble tutor typing">Elaboro…</div>
            </div>
          )}
        </div>

        {error && <div className="error-bar">{error}</div>}

        <div className="composer">
          <button type="button" className={recording ? "rec on" : "rec"} onClick={toggleRecording} disabled={busy}>
            {recording ? "■ Stop e invia" : "● Parla"}
          </button>
          {recording && autoStop && (
            <div className="meter" title="Livello del microfono">
              <div style={{ width: `${Math.round(micLevel * 100)}%` }} />
            </div>
          )}
          <form onSubmit={sendText}>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={mode === "scenario" ? "Es.: Aiutami a presentarmi in albergo per avere una camera" : "…oppure scrivi qui"}
              disabled={busy}
            />
            <button type="submit" className="send" disabled={busy || !text.trim()}>Invia</button>
          </form>
        </div>
        {recording && autoStop && (
          <div className="status">Ti ascolto… mi fermo dopo {pauseMs / 1000} s di silenzio.</div>
        )}
      </main>
    </div>
  );
}
