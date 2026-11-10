export default function Sidebar({
  open,
  mode,
  setMode,
  level,
  setLevel,
  lang,
  setLang,
  autoStop,
  setAutoStop,
  pauseMs,
  setPauseMs,
  continuous,
  setContinuous,
  hideText,
  setHideText,
  readExplanations,
  setReadExplanations,
  ttsSpeed,
  setTtsSpeed,
  onNewSession,
}) {
  return (
    <aside className={open ? "side open" : "side"}>
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
          <label className="field">
            Livello
            <select value={level} onChange={(e) => setLevel(e.target.value)}>
              {["A2", "B1", "B2", "C1"].map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </label>
        ) : (
          <label className="field">
            Parlo in
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
          <input
            type="checkbox"
            checked={autoStop}
            onChange={(e) => setAutoStop(e.target.checked)}
          />
          Stop automatico al silenzio
        </label>
        <label className="field">
          Pausa che mi ferma
          <select
            value={pauseMs}
            onChange={(e) => setPauseMs(Number(e.target.value))}
            disabled={!autoStop}
          >
            <option value={1500}>1,5 s</option>
            <option value={2500}>2,5 s</option>
            <option value={4000}>4 s (parlo lentamente)</option>
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={continuous}
            onChange={(e) => setContinuous(e.target.checked)}
            disabled={!autoStop}
          />
          Conversazione continua
        </label>
      </div>

      <div className="group">
        <h2>Ascolto</h2>
        <label className="check">
          <input
            type="checkbox"
            checked={hideText}
            onChange={(e) => setHideText(e.target.checked)}
          />
          Solo ascolto (nascondi il testo del tutor)
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={readExplanations}
            onChange={(e) => setReadExplanations(e.target.checked)}
            disabled={mode === "translate"}
          />
          Leggi le spiegazioni in italiano
        </label>
        <label className="field">
          Velocità voce inglese
          <select
            value={ttsSpeed}
            onChange={(e) => setTtsSpeed(Number(e.target.value))}
          >
            {[0.3, 0.7, 1.0].map((s) => (
              <option key={s} value={s}>
                {s.toFixed(1).replace(".", ",")}×
              </option>
            ))}
          </select>
        </label>
      </div>

      <button type="button" className="ghost" onClick={onNewSession}>
        ↺ Nuova sessione
      </button>
      <p className="muted small build">build {typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "dev"}</p>
    </aside>
  );
}
