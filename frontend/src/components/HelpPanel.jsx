export default function HelpPanel({
  helpQuestion,
  setHelpQuestion,
  helpBusy,
  helpRecording,
  helpError,
  helpResult,
  autoStop,
  pauseMs,
  onClose,
  onSendText,
  onToggleRecording,
  onPlay,
}) {
  return (
    <div
      className="help-scrim"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <aside
        className="help-panel"
        id="contextual-help"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
      >
        <header className="help-header">
          <div>
            <h2 id="help-title">Chiedi in italiano</h2>
            <p className="muted small">
              L&apos;aiuto resta qui e non interrompe la conversazione inglese.
            </p>
          </div>
          <button type="button" className="ghost" onClick={onClose} aria-label="Chiudi aiuto">
            ×
          </button>
        </header>

        <div className="help-thread" aria-live="polite">
          {!helpResult && !helpBusy && (
            <p className="muted">
              Puoi chiedere una spiegazione grammaticale o come dire una frase.
            </p>
          )}
          {helpResult && (
            <>
              <div className="help-question">{helpResult.question}</div>
              <div className="help-answer">{helpResult.answer}</div>
              {(helpResult.audio_b64 || helpResult.audio_segments?.length > 0) && (
                <button type="button" className="ghost" onClick={() => onPlay(helpResult)}>
                  🔊 Ascolta risposta
                </button>
              )}
              <span className="timings">
                {Object.entries(helpResult.timings)
                  .map(([key, value]) => `${key} ${value} s`)
                  .join(" · ")}
              </span>
            </>
          )}
          {helpBusy && <p className="muted">Preparo la spiegazione…</p>}
        </div>

        {helpError && <div className="error-bar">{helpError}</div>}
        {helpRecording && (
          <div className="status">
            Ti ascolto…{" "}
            {autoStop
              ? `stop dopo ${pauseMs / 1000} s di silenzio.`
              : "premi Stop per inviare."}
          </div>
        )}
        <form className="help-composer" onSubmit={onSendText}>
          <button
            type="button"
            className={helpRecording ? "rec on" : "rec"}
            onClick={onToggleRecording}
            disabled={helpBusy}
            aria-label={helpRecording ? "Termina domanda vocale" : "Fai una domanda a voce"}
          >
            {helpRecording ? "■ Stop" : "● Voce"}
          </button>
          <input
            value={helpQuestion}
            onChange={(event) => setHelpQuestion(event.target.value)}
            placeholder="Es.: Come si coniuga essere?"
            disabled={helpBusy || helpRecording}
          />
          <button
            type="submit"
            className="send"
            disabled={helpBusy || helpRecording || !helpQuestion.trim()}
          >
            Chiedi
          </button>
        </form>
      </aside>
    </div>
  );
}
