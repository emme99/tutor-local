import PronunciationFeedback from "./PronunciationFeedback.jsx";

/**
 * Un singolo scambio utente↔tutor nella timeline della chat.
 */
export default function TurnExchange({
  turn: t,
  hideText,
  revealed,
  onReveal,
  translations,
  practice,
  busy,
  recording,
  autoStop,
  pauseMs,
  onOpenPractice,
  onSpeakPhrase,
  onTogglePracticeRecording,
  onPlay,
  onTranslate,
}) {
  const hidden = hideText && !revealed;
  const showFix = t.mode !== "translate" && t.tutor.corrections.length > 0;
  const isPracticing = practice?.turnId === t.id;

  return (
    <div className="exchange">
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
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => onOpenPractice(t.id, t.tutor.corrected_sentence)}
                    disabled={busy || recording || practice?.recording}
                  >
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

          <div
            className={hidden ? "bubble tutor hidden" : "bubble tutor"}
            onClick={onReveal}
          >
            {hidden ? (
              "••• ascolta, poi clicca per leggere"
            ) : (
              <>
                <div>{t.tutor.reply}</div>
                {t.tutor.follow_up && <div className="follow">{t.tutor.follow_up}</div>}
              </>
            )}
          </div>

          {t.mode !== "translate" && t.tutor.suggested_reply && (
            <div className="suggested-reply">
              <div>
                <b>Puoi rispondere:</b> {t.tutor.suggested_reply}
              </div>
              <button
                type="button"
                className="ghost"
                onClick={() => onOpenPractice(t.id, t.tutor.suggested_reply)}
                disabled={busy || recording || practice?.recording}
              >
                🔊 Ascolta e prova a rispondere
              </button>
            </div>
          )}

          {isPracticing && (
            <div className="practice">
              <div className="practice-target">
                <b>Obiettivo:</b> {practice.target}
              </div>
              <div className="actions">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => onSpeakPhrase(practice.target)}
                  disabled={practice.recording || practice.loading}
                >
                  🔊 Ascolta modello
                </button>
                <button
                  type="button"
                  className={practice.recording ? "rec on" : "rec"}
                  onClick={onTogglePracticeRecording}
                  disabled={busy || recording || practice.loading}
                >
                  {practice.recording ? "■ Termina tentativo" : "● Registra ripetizione"}
                </button>
              </div>
              {practice.recording && (
                <p className="muted small">
                  Ti ascolto…{" "}
                  {autoStop
                    ? `stop dopo ${pauseMs / 1000} s di silenzio.`
                    : "premi Termina tentativo quando hai finito."}
                </p>
              )}
              {practice.loading && <p className="muted small">Confronto la frase…</p>}
              {practice.error && <p className="practice-error">{practice.error}</p>}
              {practice.result && (
                <PronunciationFeedback
                  result={practice.result}
                  onRetry={onTogglePracticeRecording}
                />
              )}
            </div>
          )}

          {translations[t.id] && (
            <div className="translation">🇮🇹 {translations[t.id]}</div>
          )}

          {t.mode === "scenario" && t.tutor.new_vocab.length > 0 && (
            <div className="phrases">
              {t.tutor.new_vocab.map((v) => (
                <div key={v.term} className="phrase">
                  <button
                    type="button"
                    className="icon"
                    onClick={() => onSpeakPhrase(v.term)}
                    title="Ascolta"
                  >
                    🔊
                  </button>
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
                <span key={v.term} title={v.example}>
                  {v.term} = {v.translation_it}
                </span>
              ))}
            </div>
          )}

          <div className="actions">
            {(t.audio_b64 || t.explanations_audio_segments?.length > 0) && (
              <button type="button" className="ghost" onClick={() => onPlay(t)}>
                🔊 Ascolta di nuovo
              </button>
            )}
            <button type="button" className="ghost" onClick={() => onTranslate(t)}>
              🇮🇹 Traduci
            </button>
            <span className="timings">
              {Object.entries(t.timings)
                .map(([k, v]) => `${k} ${v}${k.includes("tok") ? "" : " s"}`)
                .join(" · ")}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
