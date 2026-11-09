/**
 * PronunciationFeedback.jsx
 *
 * Componente che visualizza il risultato di una valutazione fonetica.
 *
 * Props:
 *   result   {object}   – oggetto PronunciationCheck restituito dal backend
 *   onRetry  {function} – callback opzionale per ripetere la registrazione
 */

import { useState } from "react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function scoreTone(score) {
  if (score >= 70) return "green";
  if (score >= 45) return "yellow";
  return "red";
}

function verdictLabel(verdict) {
  switch (verdict) {
    case "ok":
      return { icon: "✓", label: "Ci sei", cls: "pf-verdict-ok" };
    case "dubbio":
      return { icon: "~", label: "Dubbio", cls: "pf-verdict-dubbio" };
    case "da_rivedere":
      return { icon: "✗", label: "Da rivedere", cls: "pf-verdict-rivedere" };
    default:
      return null;
  }
}

function wordStateCls(word) {
  if (!word.ops || word.ops.length === 0) return "ok";
  const hasError = word.ops.some((op) => op.op !== "match");
  if (!hasError) return "ok";
  // score < 50 → rivedere, altrimenti dubbio
  return word.score < 50 ? "rivedere" : "dubbio";
}

// Simbolo da mostrare nella riga IPA allineata
function OpSymbol({ op }) {
  if (op.op === "match") {
    return <span className="pf-sym pf-sym-match">{op.expected}</span>;
  }
  if (op.op === "sub") {
    return (
      <span className="pf-sym pf-sym-sub" title={`udito: ${op.heard}`}>
        {op.expected}
      </span>
    );
  }
  if (op.op === "del") {
    return (
      <span className="pf-sym pf-sym-del" title="non udito">
        {op.expected}
      </span>
    );
  }
  if (op.op === "ins") {
    return (
      <span className="pf-sym pf-sym-ins" title={`inserito: ${op.heard}`}>
        —
      </span>
    );
  }
  return null;
}

// Rappresentazione testuale delle differenze
function diffSummary(ops) {
  const diffs = ops
    .filter((op) => op.op !== "match")
    .map((op) => {
      if (op.op === "sub") return `/${op.expected}/→/${op.heard}/`;
      if (op.op === "del") return `/${op.expected}/ omesso`;
      if (op.op === "ins") return `/${op.heard}/ aggiunto`;
      return "";
    })
    .filter(Boolean);
  return diffs.length > 0 ? diffs.join(", ") : null;
}

// ---------------------------------------------------------------------------
// Sub-componenti
// ---------------------------------------------------------------------------

/** Visualizzazione per target brevi (verdict mode) */
function ShortTargetView({ result }) {
  const vd = verdictLabel(result.verdict);
  const diffs = diffSummary(result.ops || []);

  return (
    <div className="pf-short">
      {vd && (
        <span className={`pf-verdict-badge ${vd.cls}`}>
          {vd.icon} {vd.label}
        </span>
      )}

      {/* Riga IPA allineata: simboli attesi con highlight delle differenze */}
      <div className="pf-ipa-block">
        <div className="pf-ipa-row">
          <span className="pf-ipa-label">Atteso:</span>
          <span className="pf-ipa-syms">
            {(result.ops || []).map((op, i) =>
              op.op !== "ins" ? (
                <OpSymbol key={i} op={op} />
              ) : null
            )}
          </span>
        </div>
        <div className="pf-ipa-row">
          <span className="pf-ipa-label">Udito:</span>
          <span className="pf-ipa-syms">
            {(result.ops || []).map((op, i) => {
              if (op.op === "del") {
                return (
                  <span key={i} className="pf-sym pf-sym-del">
                    —
                  </span>
                );
              }
              if (op.op === "match") {
                return (
                  <span key={i} className="pf-sym pf-sym-match">
                    {op.heard}
                  </span>
                );
              }
              if (op.op === "sub") {
                return (
                  <span key={i} className="pf-sym pf-sym-sub">
                    {op.heard}
                  </span>
                );
              }
              if (op.op === "ins") {
                return (
                  <span key={i} className="pf-sym pf-sym-ins">
                    {op.heard}
                  </span>
                );
              }
              return null;
            })}
          </span>
        </div>
      </div>

      {diffs && (
        <p className="pf-diffs muted small">Differenze: {diffs}</p>
      )}

      {result.verdict === "da_rivedere" && (
        <p className="muted small pf-short-caveat">
          Il riconoscitore può sbagliare sulle parole brevi: riprova una volta e
          confronta.
        </p>
      )}
    </div>
  );
}

/** Chip per una singola parola (target lunghi) */
function WordChip({ word, issuesByWord }) {
  const [open, setOpen] = useState(false);
  const cls = wordStateCls(word);
  const issue = issuesByWord[word.word];

  return (
    <span className="pf-word-wrap">
      <button
        type="button"
        className={`pf-word-chip ${cls}`}
        onClick={() => setOpen((v) => !v)}
        title={cls !== "ok" ? "Clicca per dettagli" : undefined}
      >
        {word.word}
        {cls === "rivedere" && <span className="pf-word-icon"> ⚠</span>}
        {cls === "dubbio" && <span className="pf-word-icon"> ~</span>}
      </button>
      {open && (
        <div className="pf-word-detail">
          <p className="pf-detail-line">
            <span className="ipa-label">Atteso:</span> {word.expected_ipa}
          </p>
          <p className="pf-detail-line">
            <span className="ipa-label">Udito:</span>{" "}
            {word.heard_ipa || <em className="muted">—</em>}
          </p>
          {issue && (
            <p className="pf-detail-tip">{issue.tip_it}</p>
          )}
        </div>
      )}
    </span>
  );
}

/** Visualizzazione per target lunghi (score + parola per parola) */
function LongTargetView({ result }) {
  // Mappa parola → prima issue relativa
  const issuesByWord = {};
  for (const issue of result.issues || []) {
    if (!issuesByWord[issue.word]) {
      issuesByWord[issue.word] = issue;
    }
  }

  // Max 2 tips da mostrare globalmente
  const topIssues = (result.issues || []).slice(0, 2);

  return (
    <div className="pf-long">
      <p>
        <span className={`score-badge ${scoreTone(result.score)}`}>
          {result.score}/100
        </span>{" "}
        <span className="muted small">
          Fonemi corretti: {result.matched_phones}/{result.total_phones}
        </span>
      </p>

      {/* Parole colorate per stato */}
      <div className="pf-words">
        {(result.words || []).map((w, i) => (
          <WordChip key={i} word={w} issuesByWord={issuesByWord} />
        ))}
      </div>

      {/* Tips fonetici */}
      {topIssues.length > 0 && (
        <div className="pf-tips">
          {topIssues.map((issue, i) => (
            <p key={i} className={`pf-tip pf-tip-${issue.severity}`}>
              💡 {issue.tip_it}
            </p>
          ))}
        </div>
      )}

      {/* Disclaimer */}
      <p className="muted small pf-disclaimer">
        Indicazione automatica: può sbagliare; non valuta accento né prosodia.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principale
// ---------------------------------------------------------------------------

export default function PronunciationFeedback({ result, onRetry }) {
  if (!result) return null;

  return (
    <div className="pf-root">
      {result.short_target ? (
        <ShortTargetView result={result} />
      ) : (
        <LongTargetView result={result} />
      )}
    </div>
  );
}

