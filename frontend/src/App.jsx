import { useEffect, useRef, useState } from "react";
import { startVAD } from "./vad.js";
import { useAudioPlayer } from "./hooks/useAudioPlayer.js";
import { MODE_HINTS, reviewSpeechText } from "./utils.js";
import Sidebar from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";
import Composer from "./components/Composer.jsx";
import TurnExchange from "./components/TurnExchange.jsx";
import HelpPanel from "./components/HelpPanel.jsx";
import ReviewPanel from "./components/ReviewPanel.jsx";

let nextId = 1;

export default function App() {
  const [session, setSession] = useState(() => crypto.randomUUID());
  const [mode, setMode] = useState("conversation");
  const [level, setLevel] = useState("B1");
  const [lang, setLang] = useState("en");
  const [autoStop, setAutoStop] = useState(true);
  const [pauseMs, setPauseMs] = useState(2500);
  const [continuous, setContinuous] = useState(false);
  const [readExplanations, setReadExplanations] = useState(false);
  const [ttsSpeed, setTtsSpeed] = useState(1.0);
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
  cfg.current = { session, mode, level, lang, autoStop, pauseMs, continuous, readExplanations, ttsSpeed };

  const { play, stop: stopAudio } = useAudioPlayer();

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  useEffect(() => {
    refreshReviewStats();
  }, []);

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") {
        if (helpOpen) closeHelp();
        else if (reviewOpen) closeReview();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [helpOpen, reviewOpen]);

  async function refreshReviewStats() {
    try {
      const response = await fetch("/api/review/stats");
      if (response.ok) setReviewStats(await response.json());
    } catch {
      /* il badge non è essenziale: se il backend non risponde lo si aggiorna al prossimo turno */
    }
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
      form.append("tts_speed", c.ttsSpeed);
      const r = await fetch("/api/turn", { method: "POST", body: form });
      if (!r.ok) {
        let msg = r.statusText;
        try {
          msg = (await r.json()).detail || msg;
        } catch {
          /* corpo non JSON */
        }
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
    stopAudio(); // niente voce del tutor nel microfono
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
        body: JSON.stringify({ text: phrase, lang: "en", speed: cfg.current.ttsSpeed }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || r.statusText);
      play({ audio_b64: d.audio_b64, audio_mime: d.audio_mime });
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  function openPractice(turnId, target) {
    stopAudio();
    setPractice({ turnId, target, recording: false, loading: false, result: null, error: "" });
    speakPhrase(target);
  }

  async function startPracticeRecording() {
    if (!practice || practiceRecorder.current?.state === "recording") return;
    const { turnId, target } = practice;
    stopAudio();
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
        setPractice((current) =>
          current?.turnId === turnId
            ? { ...current, recording: false, loading: true, error: "", result: null }
            : current
        );
        const form = new FormData();
        form.append("target", target);
        form.append("audio", new Blob(practiceChunks.current, { type: mr.mimeType }), "practice.webm");
        try {
          const response = await fetch("/api/pronunciation-check", { method: "POST", body: form });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || response.statusText);
          setPractice((current) =>
            current?.turnId === turnId ? { ...current, loading: false, result: data } : current
          );
        } catch (e) {
          setPractice((current) =>
            current?.turnId === turnId
              ? { ...current, loading: false, error: String(e.message || e) }
              : current
          );
        }
      };
      mr.start();
      practiceRecorder.current = mr;
      setPractice((current) =>
        current?.turnId === turnId
          ? { ...current, recording: true, loading: false, result: null, error: "" }
          : current
      );
      if (cfg.current.autoStop) {
        stopPracticeVad.current = startVAD(stream, {
          silenceMs: cfg.current.pauseMs,
          onLevel: () => {},
          onStop: () => mr.state === "recording" && mr.stop(),
        });
      }
    } catch (e) {
      setPractice((current) =>
        current?.turnId === turnId
          ? { ...current, error: "Microfono non disponibile: " + e.message }
          : current
      );
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
    stopAudio();
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
    form.append("tts_speed", cfg.current.ttsSpeed);
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
    stopAudio();
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
    const phrase = reviewSpeechText(item);
    if (!phrase || reviewAudioBusy) return;
    setReviewAudioBusy(true);
    setReviewError("");
    try {
      const response = await fetch("/api/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: phrase, lang: "en", speed: cfg.current.ttsSpeed }),
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
    stopAudio();
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
        setReviewPractice((current) =>
          current?.itemId === item.id
            ? { ...current, recording: false, loading: true, error: "", result: null }
            : current
        );
        const form = new FormData();
        form.append("target", target);
        form.append("audio", new Blob(reviewChunks.current, { type: mr.mimeType }), "review.webm");
        try {
          const response = await fetch("/api/pronunciation-check", { method: "POST", body: form });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || response.statusText);
          setReviewPractice((current) =>
            current?.itemId === item.id ? { ...current, loading: false, result: data } : current
          );
        } catch (e) {
          setReviewPractice((current) =>
            current?.itemId === item.id
              ? { ...current, loading: false, error: String(e.message || e) }
              : current
          );
        }
      };
      mr.start();
      reviewRecorder.current = mr;
      setReviewPractice({
        itemId: item.id,
        target,
        recording: true,
        loading: false,
        result: null,
        error: "",
      });
      if (cfg.current.autoStop) {
        stopReviewVad.current = startVAD(stream, {
          silenceMs: cfg.current.pauseMs,
          onLevel: () => {},
          onStop: () => mr.state === "recording" && mr.stop(),
        });
      }
    } catch (e) {
      setReviewPractice({
        itemId: item.id,
        target,
        recording: false,
        loading: false,
        result: null,
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
      setReview((current) =>
        current
          ? {
              ...current,
              items: current.items.filter((entry) => entry.id !== item.id),
              due_count: data.due_count,
              total: data.total,
            }
          : current
      );
      setReviewStats({ due_count: data.due_count, total: data.total });
      setReviewRevealed(false);
    } catch (e) {
      setReviewError(String(e.message || e));
    } finally {
      setReviewBusy(false);
    }
  }

  const currentReview = review?.items?.[0];
  const reviewAttempt = reviewPractice?.itemId === currentReview?.id ? reviewPractice : null;
  const reviewListenLabel =
    currentReview?.kind === "mistake" ? "🔊 Ascolta frase corretta" : "🔊 Ascolta termine";

  return (
    <div className="app">
      <Sidebar
        open={sideOpen}
        mode={mode}
        setMode={setMode}
        level={level}
        setLevel={setLevel}
        lang={lang}
        setLang={setLang}
        autoStop={autoStop}
        setAutoStop={setAutoStop}
        pauseMs={pauseMs}
        setPauseMs={setPauseMs}
        continuous={continuous}
        setContinuous={setContinuous}
        hideText={hideText}
        setHideText={setHideText}
        readExplanations={readExplanations}
        setReadExplanations={setReadExplanations}
        ttsSpeed={ttsSpeed}
        setTtsSpeed={setTtsSpeed}
        onNewSession={newSession}
      />

      {sideOpen && <div className="scrim" onClick={() => setSideOpen(false)} />}

      <main className="chat">
        <TopBar
          mode={mode}
          level={level}
          lang={lang}
          helpOpen={helpOpen}
          reviewOpen={reviewOpen}
          reviewDueCount={reviewStats.due_count}
          onOpenMenu={() => setSideOpen(true)}
          onOpenHelp={openHelp}
          onOpenReview={openReview}
        />

        <div className="messages" ref={listRef}>
          {turns.length === 0 && <p className="empty">{MODE_HINTS[mode]}</p>}

          {turns.map((t) => (
            <TurnExchange
              key={t.id}
              turn={t}
              hideText={hideText}
              revealed={!!revealed[t.id]}
              onReveal={() => hideText && setRevealed((r) => ({ ...r, [t.id]: true }))}
              translations={translations}
              practice={practice}
              busy={busy}
              recording={recording}
              autoStop={autoStop}
              pauseMs={pauseMs}
              onOpenPractice={openPractice}
              onSpeakPhrase={speakPhrase}
              onTogglePracticeRecording={togglePracticeRecording}
              onPlay={play}
              onTranslate={translate}
            />
          ))}

          {busy && (
            <div className="row tutor">
              <div className="bubble tutor typing">Elaboro…</div>
            </div>
          )}
        </div>

        <Composer
          text={text}
          setText={setText}
          recording={recording}
          busy={busy}
          micLevel={micLevel}
          autoStop={autoStop}
          pauseMs={pauseMs}
          error={error}
          mode={mode}
          onToggleRecording={toggleRecording}
          onSendText={sendText}
        />
      </main>

      {helpOpen && (
        <HelpPanel
          helpQuestion={helpQuestion}
          setHelpQuestion={setHelpQuestion}
          helpBusy={helpBusy}
          helpRecording={helpRecording}
          helpError={helpError}
          helpResult={helpResult}
          autoStop={autoStop}
          pauseMs={pauseMs}
          onClose={closeHelp}
          onSendText={sendHelpText}
          onToggleRecording={toggleHelpRecording}
          onPlay={play}
        />
      )}

      {reviewOpen && (
        <ReviewPanel
          review={review}
          reviewBusy={reviewBusy}
          reviewError={reviewError}
          reviewRevealed={reviewRevealed}
          setReviewRevealed={setReviewRevealed}
          summary={summary}
          autoStop={autoStop}
          pauseMs={pauseMs}
          reviewAudioBusy={reviewAudioBusy}
          reviewAttempt={reviewAttempt}
          reviewListenLabel={reviewListenLabel}
          onClose={closeReview}
          onSpeakReview={speakReview}
          onToggleReviewRecording={toggleReviewRecording}
          onGrade={gradeReview}
        />
      )}
    </div>
  );
}
