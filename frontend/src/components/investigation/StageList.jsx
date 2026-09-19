const MARK = { done: "✓", failed: "✕", skipped: "–", pending: "" };

export default function StageList({ stages }) {
  return (
    <ol className="stages">
      {stages.map((stage) => (
        <li key={stage.key} className={`stages__item is-${stage.status}`}>
          <span className="stages__mark mono">
            {stage.status === "running" ? <span className="spinner" /> : MARK[stage.status]}
          </span>
          <span className="stages__label">
            {stage.label}
            {stage.detail && <small>{stage.detail}</small>}
          </span>
          <span className="stages__time mono">
            {stage.seconds != null ? `${stage.seconds.toFixed(1)}s` : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}
