import PronunciationFeedback from "./PronunciationFeedback.jsx";

export default function ReviewPanel({
  review,
  reviewBusy,
  reviewError,
  reviewRevealed,
  setReviewRevealed,
  summary,
  autoStop,
  pauseMs,
  reviewAudioBusy,
  reviewAttempt,
  reviewListenLabel,
  onClose,
  onSpeakReview,
  onToggleReviewRecording,
  onGrade,
}) {
  const currentReview = review?.items?.[0];

  return (
    <div
      className="help-scrim"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <aside
        className="help-panel"
        id="review-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-title"
      >
        <header className="help-header">
          <div>
            <h2 id="review-title">Ripasso</h2>
            <p className="muted small">
              Errori e vocaboli tornano al momento giusto, senza interrompere la conversazione.
            </p>
          </div>
          <button type="button" className="ghost" onClick={onClose} aria-label="Chiudi ripasso">
            ×
          </button>
        </header>

        {reviewBusy && !review && <p className="muted">Carico il ripasso…</p>}
        {reviewError && <div className="error-bar">{reviewError}</div>}

        {review && !currentReview && (
          <p className="muted">
            Nessun elemento in scadenza. Torna dopo qualche conversazione.
          </p>
        )}

        {currentReview && (
          <div className="review-card">
            <div className="muted small">
              {currentReview.kind === "mistake" ? "Errore" : "Vocabolario"}
            </div>
            <div className="review-prompt">{currentReview.prompt}</div>
            {reviewRevealed ? (
              <>
                <div className="review-answer">{currentReview.answer}</div>
                {currentReview.hint && (
                  <p className="muted small">{currentReview.hint}</p>
                )}
                <div className="review-actions actions">
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => onSpeakReview(currentReview)}
                    disabled={reviewAudioBusy || reviewAttempt?.recording}
                  >
                    {reviewListenLabel}
                  </button>
                  <button
                    type="button"
                    className={reviewAttempt?.recording ? "rec on" : "rec"}
                    onClick={onToggleReviewRecording}
                    disabled={reviewBusy || reviewAudioBusy || reviewAttempt?.loading}
                  >
                    {reviewAttempt?.recording
                      ? "■ Termina"
                      : "● Registra ripetizione"}
                  </button>
                </div>
                {reviewAttempt?.recording && (
                  <p className="muted small">
                    Ti ascolto…{" "}
                    {autoStop
                      ? `stop dopo ${pauseMs / 1000} s di silenzio.`
                      : "premi Termina quando hai finito."}
                  </p>
                )}
                {reviewAttempt?.loading && (
                  <p className="muted small">Confronto la pronuncia…</p>
                )}
                {reviewAttempt?.error && (
                  <p className="practice-error">{reviewAttempt.error}</p>
                )}
                {reviewAttempt?.result && (
                  <PronunciationFeedback
                    result={reviewAttempt.result}
                    onRetry={onToggleReviewRecording}
                  />
                )}
                <div className="grades">
                  {[
                    ["Non ricordavo", 0],
                    ["Difficile", 1],
                    ["Bene", 2],
                    ["Facile", 3],
                  ].map(([label, value]) => (
                    <button
                      key={value}
                      type="button"
                      className="ghost"
                      onClick={() => onGrade(value)}
                      disabled={reviewBusy}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <button
                type="button"
                className="ghost"
                onClick={() => setReviewRevealed(true)}
              >
                Mostra risposta
              </button>
            )}
            <p className="muted small">
              In coda: {review.items.length} · totale {review.total}
            </p>
          </div>
        )}

        {summary && summary.turns > 0 && (
          <section className="review-summary">
            <h3>Riepilogo sessione</h3>
            <p className="muted small">
              {summary.turns} turni · {summary.corrections.length} correzioni ·{" "}
              {summary.vocab.length} vocaboli
            </p>
            {summary.corrections.length > 0 && (
              <div>
                <b>Da rivedere</b>
                <ul>
                  {summary.corrections.slice(0, 6).map((correction, index) => (
                    <li key={index}>
                      {correction.original} → {correction.corrected}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {summary.vocab.length > 0 && (
              <div>
                <b>Vocaboli</b>
                <ul>
                  {summary.vocab.slice(0, 8).map((item, index) => (
                    <li key={index}>
                      {item.term} = {item.translation_it}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </aside>
    </div>
  );
}
