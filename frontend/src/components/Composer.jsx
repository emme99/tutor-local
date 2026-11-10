export default function Composer({
  text,
  setText,
  recording,
  busy,
  micLevel,
  autoStop,
  pauseMs,
  error,
  mode,
  onToggleRecording,
  onSendText,
}) {
  return (
    <>
      {error && <div className="error-bar">{error}</div>}

      <div className="composer">
        <button
          type="button"
          className={recording ? "rec on" : "rec"}
          onClick={onToggleRecording}
          disabled={busy}
        >
          {recording ? "■ Stop e invia" : "● Parla"}
        </button>
        {recording && autoStop && (
          <div className="meter" title="Livello del microfono">
            <div style={{ width: `${Math.round(micLevel * 100)}%` }} />
          </div>
        )}
        <form onSubmit={onSendText}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              mode === "scenario"
                ? "Es.: Aiutami a presentarmi in albergo per avere una camera"
                : "…oppure scrivi qui"
            }
            disabled={busy}
          />
          <button type="submit" className="send" disabled={busy || !text.trim()}>
            Invia
          </button>
        </form>
      </div>
      {recording && autoStop && (
        <div className="status">
          Ti ascolto… mi fermo dopo {pauseMs / 1000} s di silenzio.
        </div>
      )}
    </>
  );
}
