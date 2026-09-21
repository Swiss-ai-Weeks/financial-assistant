/** Where a model runs decides whether a prompt leaves the machine. */
export function Residency({ local, verbose = false }) {
  if (local == null) return null;

  return (
    <span className="compare__residency">
      <span className={`chip compare__chip ${local ? "is-local" : "is-external"}`}>
        {local ? "Local" : "External"}
      </span>
      {verbose && (
        <span className="muted">
          {local ? "prompts stay on this machine" : "leaves the machine"}
        </span>
      )}
    </span>
  );
}

/** The configured readers: who they are, where they run, whether they answer. */
export default function CompareModels({ models }) {
  if (!models) {
    return (
      <p className="compare__note muted">The model registry has not answered yet.</p>
    );
  }

  if (!models.models?.length) {
    return <p className="compare__note muted">No model is configured.</p>;
  }

  return (
    <section className="compare__readers">
      <div className="compare__readers-head">
        <span className="eyebrow">Configured models</span>

        {models.egress_policy === "local_only" && (
          <span className="compare__egress">
            <span className="chip compare__chip is-local">Egress · local only</span>
            <span className="muted">
              External models are blocked: no prompt leaves this machine.
            </span>
          </span>
        )}
      </div>

      <ul className="compare__reader-list">
        {models.models.map((model) => (
          <li key={model.id} className="compare__reader">
            <div className="compare__reader-head">
              <span
                className={`dot ${model.online ? "dot--on" : "dot--off"}`}
                title={model.detail ?? (model.online ? "online" : "offline")}
              />
              <span className="compare__strong">{model.label}</span>
              {(model.default || model.id === models.default_id) && (
                <span className="eyebrow">Default</span>
              )}
            </div>

            {model.origin && <p className="compare__origin muted">{model.origin}</p>}

            <p className="compare__model-id mono">{model.model}</p>

            <Residency local={model.local} verbose />
          </li>
        ))}
      </ul>
    </section>
  );
}
