import { useEffect, useRef, useState } from "react";
import { startVAD } from "./vad.js";

let nextId = 1;

function reviewSpeechText(item) {
  // Per gli errori si ascolta la forma corretta; per i vocaboli il termine inglese, non la traduzione.
  return item?.kind === "mistake" ? item.answer : item.prompt;
}

function scoreTone(score) {
  // Soglie tarate sul parlato accentato reale (fase 2): "buono" ~70, non ~90.
  if (score >= 70) return "score-good";
  if (score >= 45) return "score-mid";
  return "score-low";
}

export default function App() {
  const [session, setSession] = useState(() => crypto.randomUUID());
  const [mode, setMode] = useState("conversation");
  const [level, setLevel] = useState("B1");
  const [lang, setLang] = useState("en");
  const [autoStop, setAutoStop] = useState(true);
  const [pauseMs, setPauseMs] = useState(2500);
  const [continuous, setContinuous] = useState(false);
  const [readExplanations, setReadExplanations] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpQuestion, setHelpQuestion] = useState("");
  const [helpBusy, setHelpBusy] = useState(false);
  const [helpRecording, setHelpRecording] = useState(false);
  const [helpError, setHelpError] = useState("");
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
  const [practice, setPractice] = useState(null);
  const [helpResult, setHelpResult] = useState(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [review, setReview] = useState(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [reviewRevealed, setReviewRevealed] = useState(false);
  const [reviewStats, setReviewStats] = useState({ due_count: 0, total: 0 });
  const [summary, setSummary] = useState(null);
  const [reviewAudioBusy, setReviewAudioBusy] = useState(false);
  const [reviewPractice, setReviewPractice] = useState(null);

  const recorder = useRef(null);
  const chunks = useRef([]);
  const player = useRef(null);
  const stopVad = useRef(null);
  const discardRecording = useRef(false);
  const practiceRecorder = useRef(null);
  const practiceChunks = useRef([]);
  const stopPracticeVad = useRef(null);
  const discardPracticeRecording = useRef(false);
  const helpRecorder = useRef(null);
  const helpChunks = useRef([]);
  const stopHelpVad = useRef(null);
  const discardHelpRecording = useRef(false);
  const reviewRecorder = useRef(null);
  const reviewChunks = useRef([]);
  const stopReviewVad = useRef(null);
  const discardReviewRecording = useRef(false);
  const listRef = useRef(null);
  // Le callback asincrone (fine registrazione, fine audio) leggono sempre le impostazioni correnti da qui.
  const cfg = useRef({});
  cfg.current = { session, mode, level, lang, autoStop, pauseMs, continuous, readExplanations };

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  useEffect(() => {
    refreshReviewStats();
  }, []);

  async function refreshReviewStats() {
    try {
      const response = await fetch("/api/review/stats");
      if (response.ok) setReviewStats(await response.json());
    } catch {
      /* il badge non è essenziale: se il backend non risponde lo si aggiorna al prossimo turno */
    }
  }

  function play(t, onEnd) {
    const clips = [
      t.audio_b64 && { audio_b64: t.audio_b64, audio_mime: t.audio_mime },
      ...(t.explanations_audio_segments || []),
      ...(t.audio_segments || []),
    ].filter(Boolean);
    if (!clips.length) {
      onEnd?.();
      return;
    }
    player.current?.pause();
    let index = 0;
    const playNext = () => {
      if (index >= clips.length) {
        onEnd?.();
        return;
      }
      const clip = clips[index++];
      const a = new Audio(`data:${clip.audio_mime};base64,${clip.audio_b64}`);
      player.current = a;
      a.onended = playNext;
      a.play().catch(playNext);
    };
    playNext();
  }

  async function submit(form) {
    const c = cfg.current;
    setBusy(true);
    setError("");
    form.append("session_id", c.session);
    try {
      form.append("mode", c.mode);
      form.append("level", c.level);
      form.append("spoken_lang", c.lang);
      form.append("speak_explanations", c.readExplanations);
      const r = await fetch("/api/turn", { method: "POST", body: form });
      if (!r.ok) {
        let msg = r.statusText;
        try { msg = (await r.json()).detail || msg; } catch { /* corpo non JSON */ }
        throw new Error(msg);
      }
      const data = await r.json();
      if (cfg.current.session !== c.session) return; // sessione cambiata mentre la richiesta era in corso
      data.id = nextId++;
      setTurns((t) => [...t, data]);
      refreshReviewStats();
      // In "conversazione continua" quando il tutor ha finito di parlare si riascolta da soli.
      play(data, cfg.current.continuous ? () => cfg.current.continuous && startRecording() : undefined);
    } catch (e) {
      if (cfg.current.session === c.session) {
        setError(String(e.message || e));
        setContinuous(false); // un errore interrompe il ciclo automatico
      }
    } finally {
      setBusy(false);
    }
  }

  async function startRecording() {
    if (recorder.current?.state === "recording") return;
    player.current?.pause(); // niente voce del tutor nel microfono
    player.current = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      discardRecording.current = false;
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      mr.onstop = () => {
        stopVad.current?.();
        stopVad.current = null;
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        setMicLevel(0);
        const discarded = discardRecording.current;
        discardRecording.current = false;
        if (discarded) return;
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

  function openPractice(turnId, target) {
    player.current?.pause();
    setPractice({ turnId, target, recording: false, loading: false, result: null, error: "" });
    speakPhrase(target);
  }

  async function startPracticeRecording() {
    if (!practice || practiceRecorder.current?.state === "recording") return;
    const { turnId, target } = practice;
    player.current?.pause();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const mr = new MediaRecorder(stream);
      practiceChunks.current = [];
      discardPracticeRecording.current = false;
      mr.ondataavailable = (e) => e.data.size && practiceChunks.current.push(e.data);
      mr.onstop = async () => {
        stopPracticeVad.current?.();
        stopPracticeVad.current = null;
        stream.getTracks().forEach((track) => track.stop());
        const discarded = discardPracticeRecording.current;
        discardPracticeRecording.current = false;
        if (discarded) return;
        setPractice((current) => current?.turnId === turnId
          ? { ...current, recording: false, loading: true, error: "", result: null }
          : current);
        const form = new FormData();
        form.append("target", target);
        form.append("audio", new Blob(practiceChunks.current, { type: mr.mimeType }), "practice.webm");
        try {
          const response = await fetch("/api/pronunciation-check", { method: "POST", body: form });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || response.statusText);
          setPractice((current) => current?.turnId === turnId
            ? { ...current, loading: false, result: data }
            : current);
        } catch (e) {
          setPractice((current) => current?.turnId === turnId
            ? { ...current, loading: false, error: String(e.message || e) }
            : current);
        }
      };
      mr.start();
      practiceRecorder.current = mr;
      setPractice((current) => current?.turnId === turnId
        ? { ...current, recording: true, loading: false, result: null, error: "" }
        : current);
      if (cfg.current.autoStop) {
        stopPracticeVad.current = startVAD(stream, {
          silenceMs: cfg.current.pauseMs,
          onLevel: () => {},
          onStop: () => mr.state === "recording" && mr.stop(),
        });
      }
    } catch (e) {
      setPractice((current) => current?.turnId === turnId
        ? { ...current, error: "Microfono non disponibile: " + e.message }
        : current);
    }
  }

  function togglePracticeRecording() {
    if (practiceRecorder.current?.state === "recording") practiceRecorder.current.stop();
    else startPracticeRecording();
  }

  function newSession() {
    setContinuous(false);
    closeHelp();
    setHelpQuestion("");
    setHelpResult(null);
    setReviewOpen(false);
    setReview(null);
    setReviewError("");
    setReviewRevealed(false);
    setSummary(null);
    stopReviewRecording();
    setReviewPractice(null);
    setReviewAudioBusy(false);
    if (recorder.current?.state === "recording") {
      discardRecording.current = true;
      stopVad.current?.();
      stopVad.current = null;
      recorder.current.stop();
    }
    player.current?.pause();
    player.current = null;
    if (practiceRecorder.current?.state === "recording") {
      discardPracticeRecording.current = true;
      stopPracticeVad.current?.();
      stopPracticeVad.current = null;
      practiceRecorder.current.stop();
    }
    setPractice(null);
    setSession(crypto.randomUUID());
    setTurns([]);
    setTranslations({});
    setRevealed({});
    setError("");
    setBusy(false);
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

  async function submitHelp(form) {
    setHelpBusy(true);
    setHelpError("");
    setHelpResult(null);
    form.append("session_id", cfg.current.session);
    try {
      const response = await fetch("/api/help", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || response.statusText);
      setHelpResult(data);
      setHelpQuestion("");
      if (data.audio_b64) play(data);
    } catch (e) {
      setHelpError(String(e.message || e));
    } finally {
      setHelpBusy(false);
    }
  }

  function sendHelpText(e) {
    e.preventDefault();
    if (!helpQuestion.trim() || helpBusy) return;
    const form = new FormData();
    form.append("text", helpQuestion);
    submitHelp(form);
  }

  async function startHelpRecording() {
    if (helpRecorder.current?.state === "recording" || helpBusy) return;
    player.current?.pause();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const mr = new MediaRecorder(stream);
      helpChunks.current = [];
      mr.ondataavailable = (e) => e.data.size && helpChunks.current.push(e.data);
      mr.onstop = () => {
        stopHelpVad.current?.();
        stopHelpVad.current = null;
        stream.getTracks().forEach((track) => track.stop());
        setHelpRecording(false);
        if (discardHelpRecording.current) {
          discardHelpRecording.current = false;
          return;
        }
        const form = new FormData();
        form.append("audio", new Blob(helpChunks.current, { type: mr.mimeType }), "help.webm");
        submitHelp(form);
      };
      mr.start();
      helpRecorder.current = mr;
      setHelpRecording(true);
      if (cfg.current.autoStop) {
        stopHelpVad.current = startVAD(stream, {
          silenceMs: cfg.current.pauseMs,
          onLevel: () => {},
          onStop: () => mr.state === "recording" && mr.stop(),
        });
      }
    } catch (e) {
      setHelpError("Microfono non disponibile: " + e.message);
    }
  }

  function toggleHelpRecording() {
    if (helpRecorder.current?.state === "recording") helpRecorder.current.stop();
    else startHelpRecording();
  }

  function openHelp() {
    setContinuous(false);
    setReviewOpen(false);
    stopReviewRecording();
    setReviewPractice(null);
    setHelpOpen(true);
  }

  function closeHelp() {
    if (helpRecorder.current?.state === "recording") {
      discardHelpRecording.current = true;
      stopHelpVad.current?.();
      stopHelpVad.current = null;
      helpRecorder.current.stop();
    }
    setHelpOpen(false);
  }

  async function openReview() {
    setContinuous(false);
    closeHelp();
    setReviewOpen(true);
    setReviewBusy(true);
    setReviewError("");
    setReviewRevealed(false);
    stopReviewRecording();
    setReviewPractice(null);
    setReviewAudioBusy(false);
    const sid = cfg.current.session;
    const summaryPromise = fetch(`/api/session/${encodeURIComponent(sid)}/summary`)
      .then((response) => (response.ok ? response.json() : null))
      .catch(() => null);
    try {
      const response = await fetch("/api/review/due?limit=10");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || response.statusText);
      if (cfg.current.session !== sid) return;
      setReview(data);
      setReviewStats({ due_count: data.due_count, total: data.total });
      const sessionSummary = await summaryPromise;
      if (sessionSummary && cfg.current.session === sid) setSummary(sessionSummary);
    } catch (e) {
      if (cfg.current.session === sid) setReviewError(String(e.message || e));
    } finally {
      if (cfg.current.session === sid) setReviewBusy(false);
    }
  }

  function closeReview() {
    stopReviewRecording();
    setReviewPractice(null);
    setReviewOpen(false);
  }

  function stopReviewRecording(discard = true) {
    if (reviewRecorder.current?.state === "recording") {
      discardReviewRecording.current = discard;
      stopReviewVad.current?.();
      stopReviewVad.current = null;
      reviewRecorder.current.stop();
    }
  }

  async function speakReview(item) {
    const text = reviewSpeechText(item);
    if (!text || reviewAudioBusy) return;
    setReviewAudioBusy(true);
    setReviewError("");
    try {
      const response = await fetch("/api/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: "en" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || response.statusText);
      play({ audio_b64: data.audio_b64, audio_mime: data.audio_mime });
    } catch (e) {
      setReviewError(String(e.message || e));
    } finally {
      setReviewAudioBusy(false);
    }
  }

  async function startReviewRecording() {
    const item = review?.items?.[0];
    if (!item || reviewRecorder.current?.state === "recording") return;
    const target = reviewSpeechText(item);
    if (!target) {
      setReviewError("Questo elemento non ha una frase inglese da pronunciare.");
      return;
    }
    player.current?.pause();
    player.current = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const mr = new MediaRecorder(stream);
      reviewChunks.current = [];
      discardReviewRecording.current = false;
      mr.ondataavailable = (e) => e.data.size && reviewChunks.current.push(e.data);
      mr.onstop = async () => {
        stopReviewVad.current?.();
        stopReviewVad.current = null;
        stream.getTracks().forEach((track) => track.stop());
        const discarded = discardReviewRecording.current;
        discardReviewRecording.current = false;
        if (discarded) return;
        setReviewPractice((current) => current?.itemId === item.id
          ? { ...current, recording: false, loading: true, error: "", result: null }
          : current);
        const form = new FormData();
        form.append("target", target);
        form.append("audio", new Blob(reviewChunks.current, { type: mr.mimeType }), "review.webm");
        try {
          const response = await fetch("/api/pronunciation-check", { method: "POST", body: form });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || response.statusText);
          setReviewPractice((current) => current?.itemId === item.id
            ? { ...current, loading: false, result: data }
            : current);
        } catch (e) {
          setReviewPractice((current) => current?.itemId === item.id
            ? { ...current, loading: false, error: String(e.message || e) }
            : current);
        }
      };
      mr.start();
      reviewRecorder.current = mr;
      setReviewPractice({ itemId: item.id, target, recording: true, loading: false, result: null, error: "" });
      if (cfg.current.autoStop) {
        stopReviewVad.current = startVAD(stream, {
          silenceMs: cfg.current.pauseMs,
          onLevel: () => {},
          onStop: () => mr.state === "recording" && mr.stop(),
        });
      }
    } catch (e) {
      setReviewPractice({
        itemId: item.id, target, recording: false, loading: false, result: null,
        error: "Microfono non disponibile: " + e.message,
      });
    }
  }

  function toggleReviewRecording() {
    if (reviewRecorder.current?.state === "recording") reviewRecorder.current.stop();
    else startReviewRecording();
  }

  async function gradeReview(result) {
    const item = review?.items?.[0];
    if (!item || reviewBusy) return;
    stopReviewRecording();
    setReviewPractice(null);
    setReviewBusy(true);
    setReviewError("");
    try {
      const response = await fetch("/api/review/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: item.id, result }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || response.statusText);
      setReview((current) => current
        ? { ...current, items: current.items.filter((entry) => entry.id !== item.id),
            due_count: data.due_count, total: data.total }
        : current);
      setReviewStats({ due_count: data.due_count, total: data.total });
      setReviewRevealed(false);
    } catch (e) {
      setReviewError(String(e.message || e));
    } finally {
      setReviewBusy(false);
    }
  }

  const modeLabel = { conversation: "Conversazione", scenario: "Scenario", translate: "Traduzione" }[mode];
  const hints = {
    conversation: "Premi ● Parla e dì qualcosa in inglese, per esempio «My name is…». Il tutor ti risponde e ti corregge.",
    scenario: "Descrivi in italiano una situazione, per esempio «Aiutami a presentarmi in albergo per avere una camera»: riceverai le frasi da dire e poi farete un gioco di ruolo.",
    translate: "Parla (o scrivi) nella lingua scelta a sinistra: il tutor traduce e pronuncia la traduzione.",
  };
  const currentReview = review?.items?.[0];
  const reviewAttempt = reviewPractice?.itemId === currentReview?.id ? reviewPractice : null;
  const reviewListenLabel = currentReview?.kind === "mistake" ? "🔊 Ascolta frase corretta" : "🔊 Ascolta termine";

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
          <label className="check">
            <input type="checkbox" checked={readExplanations} onChange={(e) => setReadExplanations(e.target.checked)} disabled={mode === "translate"} />
            Leggi le spiegazioni in italiano
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
          <button type="button" className="ghost help-trigger" onClick={openHelp} aria-expanded={helpOpen} aria-controls="contextual-help">
            Chiedi in italiano
          </button>
          <button type="button" className="ghost" onClick={openReview} aria-expanded={reviewOpen} aria-controls="review-panel">
            🔁 Ripasso{reviewStats.due_count > 0 ? ` (${reviewStats.due_count})` : ""}
          </button>
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
                        {t.tutor.corrected_sentence && (
                          <div className="fix-line">
                            <div className="fix">✎ {t.tutor.corrected_sentence}</div>
                            <button type="button" className="ghost" onClick={() => openPractice(t.id, t.tutor.corrected_sentence)} disabled={busy || recording || practice?.recording}>
                              🔊 Ascolta frase corretta
                            </button>
                          </div>
                        )}
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

                    {t.mode !== "translate" && t.tutor.suggested_reply && (
                      <div className="suggested-reply">
                        <div><b>Puoi rispondere:</b> {t.tutor.suggested_reply}</div>
                        <button type="button" className="ghost" onClick={() => openPractice(t.id, t.tutor.suggested_reply)} disabled={busy || recording || practice?.recording}>
                          🔊 Ascolta e prova a rispondere
                        </button>
                      </div>
                    )}

                    {practice?.turnId === t.id && (
                      <div className="practice">
                        <div className="practice-target"><b>Obiettivo:</b> {practice.target}</div>
                        <div className="actions">
                          <button type="button" className="ghost" onClick={() => speakPhrase(practice.target)} disabled={practice.recording || practice.loading}>
                            🔊 Ascolta modello
                          </button>
                          <button type="button" className={practice.recording ? "rec on" : "rec"} onClick={togglePracticeRecording} disabled={busy || recording || practice.loading}>
                            {practice.recording ? "■ Termina tentativo" : "● Registra ripetizione"}
                          </button>
                        </div>
                        {practice.recording && <p className="muted small">Ti ascolto… {autoStop ? `stop dopo ${pauseMs / 1000} s di silenzio.` : "premi Termina tentativo quando hai finito."}</p>}
                        {practice.loading && <p className="muted small">Confronto la frase…</p>}
                        {practice.error && <p className="practice-error">{practice.error}</p>}
                        {practice.result && (
                          <div className="practice-result">
                            <p>
                              <span className={`score-badge ${scoreTone(practice.result.score)}`}>
                                {practice.result.score}/100
                              </span>
                              {" "}Fonemi corretti (stima): {practice.result.matched_phones}/{practice.result.total_phones}
                            </p>
                            <p className="ipa"><span className="ipa-label">Atteso:</span> {practice.result.expected_ipa}</p>
                            <p className="ipa"><span className="ipa-label">Pronunciato:</span> {practice.result.predicted_ipa}</p>
                            <p className="muted small">Confronto fonetico automatico sui fonemi; non valuta l'accento né la prosodia.</p>
                          </div>
                        )}
                      </div>
                    )}

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
                      {(t.audio_b64 || t.explanations_audio_segments?.length > 0) && <button type="button" className="ghost" onClick={() => play(t)}>🔊 Ascolta di nuovo</button>}
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

      {helpOpen && (
        <div className="help-scrim" onMouseDown={(event) => event.target === event.currentTarget && closeHelp()}>
          <aside className="help-panel" id="contextual-help" role="dialog" aria-modal="true" aria-labelledby="help-title">
            <header className="help-header">
              <div>
                <h2 id="help-title">Chiedi in italiano</h2>
                <p className="muted small">L'aiuto resta qui e non interrompe la conversazione inglese.</p>
              </div>
              <button type="button" className="ghost" onClick={closeHelp} aria-label="Chiudi aiuto">×</button>
            </header>

            <div className="help-thread" aria-live="polite">
              {!helpResult && !helpBusy && <p className="muted">Puoi chiedere una spiegazione grammaticale o come dire una frase.</p>}
              {helpResult && (
                <>
                  <div className="help-question">{helpResult.question}</div>
                  <div className="help-answer">{helpResult.answer}</div>
                  {(helpResult.audio_b64 || helpResult.audio_segments?.length > 0) && <button type="button" className="ghost" onClick={() => play(helpResult)}>🔊 Ascolta risposta</button>}
                  <span className="timings">{Object.entries(helpResult.timings).map(([key, value]) => `${key} ${value} s`).join(" · ")}</span>
                </>
              )}
              {helpBusy && <p className="muted">Preparo la spiegazione…</p>}
            </div>

            {helpError && <div className="error-bar">{helpError}</div>}
            {helpRecording && <div className="status">Ti ascolto… {autoStop ? `stop dopo ${pauseMs / 1000} s di silenzio.` : "premi Stop per inviare."}</div>}
            <form className="help-composer" onSubmit={sendHelpText}>
              <button type="button" className={helpRecording ? "rec on" : "rec"} onClick={toggleHelpRecording} disabled={helpBusy} aria-label={helpRecording ? "Termina domanda vocale" : "Fai una domanda a voce"}>
                {helpRecording ? "■ Stop" : "● Voce"}
              </button>
              <input value={helpQuestion} onChange={(event) => setHelpQuestion(event.target.value)} placeholder="Es.: Come si coniuga essere?" disabled={helpBusy || helpRecording} />
              <button type="submit" className="send" disabled={helpBusy || helpRecording || !helpQuestion.trim()}>Chiedi</button>
            </form>
          </aside>
        </div>
      )}

      {reviewOpen && (
        <div className="help-scrim" onMouseDown={(event) => event.target === event.currentTarget && closeReview()}>
          <aside className="help-panel" id="review-panel" role="dialog" aria-modal="true" aria-labelledby="review-title">
            <header className="help-header">
              <div>
                <h2 id="review-title">Ripasso</h2>
                <p className="muted small">Errori e vocaboli tornano al momento giusto, senza interrompere la conversazione.</p>
              </div>
              <button type="button" className="ghost" onClick={closeReview} aria-label="Chiudi ripasso">×</button>
            </header>

            {reviewBusy && !review && <p className="muted">Carico il ripasso…</p>}
            {reviewError && <div className="error-bar">{reviewError}</div>}

            {review && !currentReview && (
              <p className="muted">Nessun elemento in scadenza. Torna dopo qualche conversazione.</p>
            )}

            {currentReview && (
              <div className="review-card">
                <div className="muted small">
                  {currentReview.kind === "mistake" ? "Errore da correggere" : "Vocabolario da ricordare"}
                </div>
                <div className="review-prompt">{currentReview.prompt}</div>
                {!reviewRevealed ? (
                  <button type="button" className="send" onClick={() => setReviewRevealed(true)} disabled={reviewBusy}>
                    Mostra risposta
                  </button>
                ) : (
                  <>
                    <div className="review-answer">{currentReview.answer}</div>
                    {currentReview.hint && <p className="muted">{currentReview.hint}</p>}
                    <div className="actions review-actions">
                      <button type="button" className="ghost" onClick={() => speakReview(currentReview)}
                        disabled={reviewAudioBusy || reviewAttempt?.recording}>
                        {reviewAudioBusy ? "Preparo audio…" : reviewListenLabel}
                      </button>
                      <button type="button" className={reviewAttempt?.recording ? "rec on" : "rec"}
                        onClick={toggleReviewRecording} disabled={reviewAttempt?.loading || reviewAudioBusy}>
                        {reviewAttempt?.recording ? "■ Termina" : "● Ripeti"}
                      </button>
                    </div>
                    {reviewAttempt?.recording && (
                      <p className="muted small">
                        Ti ascolto… {autoStop ? `stop dopo ${pauseMs / 1000} s di silenzio.` : "premi Termina quando hai finito."}
                      </p>
                    )}
                    {reviewAttempt?.loading && <p className="muted small">Confronto la pronuncia…</p>}
                    {reviewAttempt?.error && <p className="practice-error">{reviewAttempt.error}</p>}
                    {reviewAttempt?.result && (
                      <div className="practice-result">
                        <p>
                          <span className={`score-badge ${scoreTone(reviewAttempt.result.score)}`}>
                            {reviewAttempt.result.score}/100
                          </span>
                          {" "}Fonemi corretti (stima): {reviewAttempt.result.matched_phones}/{reviewAttempt.result.total_phones}
                        </p>
                        <p className="ipa"><span className="ipa-label">Atteso:</span> {reviewAttempt.result.expected_ipa}</p>
                        <p className="ipa"><span className="ipa-label">Pronunciato:</span> {reviewAttempt.result.predicted_ipa}</p>
                        <p className="muted small">Confronto fonetico automatico sui fonemi; non valuta l'accento né la prosodia.</p>
                      </div>
                    )}
                    <div className="grades">
                      {[["Non ricordavo", 0], ["Difficile", 1], ["Bene", 2], ["Facile", 3]].map(([label, value]) => (
                        <button key={value} type="button" className="ghost" onClick={() => gradeReview(value)} disabled={reviewBusy}>
                          {label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
                <p className="muted small">In coda: {review.items.length} · totale {review.total}</p>
              </div>
            )}

            {summary && summary.turns > 0 && (
              <section className="review-summary">
                <h3>Riepilogo sessione</h3>
                <p className="muted small">
                  {summary.turns} turni · {summary.corrections.length} correzioni · {summary.vocab.length} vocaboli
                </p>
                {summary.corrections.length > 0 && (
                  <div>
                    <b>Da rivedere</b>
                    <ul>
                      {summary.corrections.slice(0, 6).map((correction, index) => (
                        <li key={index}>{correction.original} → {correction.corrected}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {summary.vocab.length > 0 && (
                  <div>
                    <b>Vocaboli</b>
                    <ul>
                      {summary.vocab.slice(0, 8).map((item, index) => (
                        <li key={index}>{item.term} = {item.translation_it}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
