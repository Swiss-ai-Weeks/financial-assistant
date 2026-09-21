import { useState } from "react";

import { labelFor } from "../../lib/claimgraph/reviewModel.js";

const ITEM_ACTIONS = [
  ["accepted", "Accept"],
  ["challenged", "Challenge"],
  ["evidence_requested", "Request evidence"],
];

const CASE_ACTIONS = [
  ["approved", "Approve for this purpose"],
  ["challenged", "Challenge"],
  ["unresolved", "Needs more work"],
];

/**
 * A person's verdict on one item, or on the whole case.
 *
 * It is an overlay: accepting a claim does not change its
 * type, satisfy a requirement or make it true. It records
 * who looked, what they decided and why.
 */
export default function ReviewActions({ item = null, state, onAction }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState(null);

  const act = (status) => {
    try {
      onAction({ status, note, item });
      setNote("");
      setError(null);
    } catch (problem) {
      setError(problem.message);
    }
  };

  const recorded = state?.status ?? state;

  return (
    <section className="review-actions">
      <span className="eyebrow">{item ? "Your review of this item" : "Your decision"}</span>

      <p className="muted">
        {recorded ? `Recorded: ${labelFor(recorded)}` : "Not reviewed yet"}
        {state?.note && (
          <>
            {" · "}
            {state.note} <small>({state.reviewer})</small>
          </>
        )}
      </p>

      <textarea
        rows={2}
        value={note}
        placeholder="Why, or which evidence you still need…"
        onChange={(event) => setNote(event.target.value)}
      />

      <div className="review-actions__buttons">
        {(item ? ITEM_ACTIONS : CASE_ACTIONS).map(([status, label]) => (
          <button
            key={status}
            className="btn btn--ghost btn--small"
            onClick={() => act(status)}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <div className="error-banner">{error}</div>}
    </section>
  );
}
