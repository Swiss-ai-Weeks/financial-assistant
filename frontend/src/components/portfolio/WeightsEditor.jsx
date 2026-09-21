import { useState } from "react";

import { api } from "../../api/client";
import {
  DEFAULT_NOTIONAL,
  SAMPLE_PORTFOLIO,
  summarizeWeights,
  validatePositions,
  weightsText,
} from "../../lib/portfolio";

/**
 * The book stated as weights rather than trades: a name, a
 * notional and one "TICKER weight" line per holding.
 *
 * A field holds a draft only while the manager is typing.
 * With no draft it shows the book itself, so a save, a reset
 * or a change made elsewhere on the desk appears here without
 * an effect copying props into state.
 */
export default function WeightsEditor({ portfolio, onSaved }) {
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(null);

  const current = weightsText(portfolio?.positions);

  const name = draft.name ?? portfolio?.name ?? "";
  const notional = draft.notional ?? String(DEFAULT_NOTIONAL);
  const text = draft.text ?? current;

  const summary = summarizeWeights(text);
  const amount = Number(notional);
  const amountValid = Number.isFinite(amount) && amount > 0;

  const edit = (patch) => {
    setDraft((previous) => ({ ...previous, ...patch }));
    setSaved(null);
  };

  const run = async (action, work, message) => {
    setBusy(action);
    setError(null);
    setSaved(null);

    try {
      await work();

      setDraft({});
      setSaved(message);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(null);
    }
  };

  const save = () => {
    let positions;

    try {
      positions = validatePositions(text);
    } catch (failure) {
      setError(failure.message);
      return;
    }

    if (!amountValid) {
      setError("The notional must be a positive amount.");
      return;
    }

    run(
      "save",
      async () => {
        await api.setWeights(positions, { name: name.trim() || undefined, notional: amount });

        onSaved({ sameWeights: weightsText(positions) === current });
      },
      "Holdings saved."
    );
  };

  const reset = () =>
    run(
      "reset",
      async () => {
        await api.resetPortfolio();

        onSaved({ sameWeights: false });
      },
      "Demo book restored."
    );

  return (
    <details className="portfolio-editor">
      <summary>
        <span className="portfolio-editor__title">Edit the book as weights</span>
        <span className="muted">
          No trade history: tickers and decimal weights, sized on a notional.
        </span>
      </summary>

      <div className="portfolio-editor__body">
        <div className="portfolio-editor__fields">
          <label className="portfolio-field">
            <span className="eyebrow">Name</span>
            <input
              value={name}
              onChange={(event) => edit({ name: event.target.value })}
              placeholder="Book name"
            />
          </label>

          <label className="portfolio-field">
            <span className="eyebrow">Notional ($)</span>
            <input
              className="mono"
              type="number"
              min="1"
              step="1000"
              value={notional}
              onChange={(event) => edit({ notional: event.target.value })}
            />
          </label>

          <p className="muted portfolio-editor__hint">
            Each weight becomes a share count at the latest visible close, so on
            a replay date the book is sized with that day’s prices. A zero
            weight drops the holding.
          </p>
        </div>

        <label className="portfolio-field portfolio-editor__weights">
          <span className="eyebrow">One ticker and decimal weight per line</span>
          <textarea
            className="mono"
            rows={Math.min(Math.max(summary.count + 1, 6), 16)}
            spellCheck={false}
            value={text}
            onChange={(event) => edit({ text: event.target.value })}
          />
          <span className={`mono portfolio-editor__total ${summary.valid ? "up" : "muted"}`}>
            {summary.count} {summary.count === 1 ? "position" : "positions"} · total{" "}
            {summary.total == null ? "—" : summary.total.toFixed(4)}
            {summary.valid ? " · valid" : " · must be unique, non-negative and sum to 1"}
          </span>
        </label>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <div className="portfolio-editor__actions">
        <button className="btn" disabled={busy != null} onClick={save}>
          {busy === "save" ? "Saving…" : "Save holdings"}
        </button>

        <button
          className="btn btn--ghost"
          disabled={busy != null}
          onClick={() => {
            setError(null);
            edit({ text: weightsText(SAMPLE_PORTFOLIO.positions), name: SAMPLE_PORTFOLIO.name });
          }}
        >
          Load sample (COHU 0.5 / PDFS 0.5)
        </button>

        <button className="btn btn--ghost" disabled={busy != null} onClick={reset}>
          {busy === "reset" ? "Restoring…" : "Reset demo book"}
        </button>

        {saved && (
          <span className="muted" role="status">
            {saved}
          </span>
        )}
      </div>
    </details>
  );
}
