import { MODE_LABEL } from "../utils.js";

export default function TopBar({
  mode,
  level,
  lang,
  helpOpen,
  reviewOpen,
  reviewDueCount,
  onOpenMenu,
  onOpenHelp,
  onOpenReview,
}) {
  const subtitle =
    mode === "translate"
      ? lang === "it"
        ? "italiano → inglese"
        : "inglese → italiano"
      : `livello ${level}`;

  return (
    <header className="topbar">
      <button type="button" className="menu ghost" onClick={onOpenMenu} aria-label="Opzioni">
        ☰
      </button>
      <strong>{MODE_LABEL[mode] || mode}</strong>
      <span className="muted small">{subtitle}</span>
      <button
        type="button"
        className="ghost help-trigger"
        onClick={onOpenHelp}
        aria-expanded={helpOpen}
        aria-controls="contextual-help"
      >
        Chiedi in italiano
      </button>
      <button
        type="button"
        className="ghost"
        onClick={onOpenReview}
        aria-expanded={reviewOpen}
        aria-controls="review-panel"
      >
        🔁 Ripasso{reviewDueCount > 0 ? ` (${reviewDueCount})` : ""}
      </button>
    </header>
  );
}
