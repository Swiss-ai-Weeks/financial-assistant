import { useEffect, useRef, useState } from "react";

import { candidates, readers } from "../../lib/claimgraph/compare";
import { shortDate } from "../../lib/format";
import { KIND_LABEL, STRATEGY_STYLE } from "../../lib/strategies";
import CompareAlignment from "./CompareAlignment";
import CompareColumn from "./CompareColumn";

function Banner({ agreement, single }) {
  if (!agreement) {
    return (
      <p className="compare__invite muted">
        {single
          ? "One model has read this anomaly so far. Run another model on the same evidence to see whether the explanation holds."
          : "Agreement appears once two models have finished with at least one explanation each."}
      </p>
    );
  }

  const count = readers(agreement);
  const who = count === 2 ? "Both models" : `All ${count} models`;

  return (
    <div className={`compare__banner ${agreement.same_best ? "is-agreed" : "is-split"}`}>
      <strong>
        {agreement.same_best
          ? `${who} rank the same explanation first`
          : "The models disagree on the best-supported explanation"}
      </strong>
      <span className="mono">
        {agreement.shared} of {agreement.total} explanations shared
      </span>
    </div>
  );
}

/** Why a model cannot be asked right now, or null when it can. */
function blocked(model, models) {
  if (!model) return "This model is no longer configured";

  if (models?.egress_policy === "local_only" && model.local === false) {
    return "Egress policy is local only: prompts may not leave this machine";
  }

  return model.online ? null : (model.detail ?? "This model is offline");
}

/** One anomaly, every model that read it, and where they meet. */
export default function CompareSection({
  group,
  runs,
  models,
  focused,
  defaultOpen,
  onOpen,
  onExplain,
}) {
  const { anomaly, columns, agreement } = group;

  const element = useRef(null);
  const [toggled, setToggled] = useState(null);
  const [pending, setPending] = useState({});
  const [error, setError] = useState(null);

  const open = toggled ?? (focused || defaultOpen);

  useEffect(() => {
    if (focused) element.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [focused]);

  function explain(key, modelId) {
    setError(null);
    setPending((known) => ({ ...known, [key]: "starting" }));

    Promise.resolve()
      .then(() => onExplain(anomaly, modelId))
      .then(
        // Stays pending until the parent's next poll brings the run in.
        () => setPending((known) => ({ ...known, [key]: "started" })),
        (reason) => {
          setPending((known) => ({ ...known, [key]: undefined }));
          setError(reason?.message ?? String(reason));
        }
      );
  }

  function retryFor(column) {
    if (column.status !== "failed") return null;

    const modelId = column.model_id === "default" ? models?.default_id : column.model_id;
    const model = models?.models?.find((item) => item.id === modelId);
    const reason = blocked(model, models);
    const state = pending[column.investigation_id];

    if (!modelId || !models) return null;

    return (
      <button
        className="btn btn--ghost btn--small compare__retry"
        disabled={reason != null || state != null}
        title={reason ?? undefined}
        onClick={() => explain(column.investigation_id, modelId)}
      >
        {state ? "Starting…" : "Try again"}
      </button>
    );
  }

  const missing = candidates(models, columns);
  const strategy = STRATEGY_STYLE[anomaly.strategy];

  return (
    <section
      ref={element}
      className={`compare__section ${focused ? "is-focused" : ""}`}
    >
      <header className="compare__section-head">
        <div className="compare__section-title">
          <h2 className="mono">
            {[anomaly.ticker, ...(anomaly.related_tickers ?? [])].join(" / ")}
          </h2>
          <span className={`chip chip--${anomaly.strategy}`}>
            {strategy?.label ?? anomaly.strategy}
          </span>
          {anomaly.kind && (
            <span className="chip">{KIND_LABEL[anomaly.kind] ?? anomaly.kind}</span>
          )}
          {anomaly.observed_on && (
            <span className="chip">{shortDate(anomaly.observed_on)}</span>
          )}

          <span className="compare__section-count mono muted">
            {columns.length} {columns.length === 1 ? "model" : "models"}
          </span>
          <button
            className="btn btn--ghost btn--small"
            aria-expanded={open}
            onClick={() => setToggled(!open)}
          >
            {open ? "Hide" : "Show"}
          </button>
        </div>

        {anomaly.summary && <p className="muted">{anomaly.summary}</p>}
      </header>

      {open && (
        <div className="compare__body">
          <Banner agreement={agreement} single={columns.length === 1} />

          <div className="compare__scroll">
            <div className="compare__columns" data-count={Math.min(columns.length, 4)}>
              {columns.map((column) => (
                <CompareColumn
                  key={column.model_id}
                  column={column}
                  run={runs.get(column.investigation_id)}
                  retry={retryFor(column)}
                  onOpen={onOpen}
                />
              ))}
            </div>
          </div>

          {agreement && <CompareAlignment agreement={agreement} columns={columns} />}

          {missing.length > 0 && (
            <div className="compare__explain">
              <span className="eyebrow">Read the same evidence with</span>

              <div className="compare__explain-buttons">
                {missing.map((model) => {
                  const reason = blocked(model, models);
                  const state = pending[model.id];

                  return (
                    <button
                      key={model.id}
                      className="btn btn--ghost btn--small"
                      disabled={reason != null || state != null}
                      title={reason ?? undefined}
                      onClick={() => explain(model.id, model.id)}
                    >
                      {state && <span className="spinner" />}
                      {state === "starting"
                        ? `Asking ${model.label}…`
                        : state === "started"
                          ? `${model.label} is reading…`
                          : `Explain with ${model.label}`}
                      {!state && reason != null && (
                        <span className="dot dot--off" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {error && <div className="error-banner compare__error">{error}</div>}
        </div>
      )}
    </section>
  );
}
