import { dateTime } from "../../lib/format";
import { STRATEGY_STYLE } from "../../lib/strategies";

export default function InvestigationsTable({ investigations, onOpen }) {
  if (!investigations?.length) {
    return (
      <div className="empty">
        No investigation yet. Select an anomaly and ask Nemotron to explain it.
      </div>
    );
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Started (UTC)</th>
          <th>Market</th>
          <th>Monitor</th>
          <th>Model</th>
          <th>Status</th>
          <th className="num">Articles</th>
          <th className="num">Claims</th>
          <th>Best supported explanation</th>
        </tr>
      </thead>
      <tbody>
        {investigations.map((run) => (
          <tr key={run.investigation_id} onClick={() => onOpen(run)}>
            <td className="mono">{dateTime(run.created_at)}</td>
            <td className="mono strong">
              {[run.anomaly.ticker, ...run.anomaly.related_tickers].join(" / ")}
            </td>
            <td>
              <span className={`chip chip--${run.anomaly.strategy}`}>
                {STRATEGY_STYLE[run.anomaly.strategy].label}
              </span>
            </td>
            <td className="mono">{run.model_label || run.model.split("/").pop()}</td>
            <td className={`mono status status--${run.status}`}>{run.status}</td>
            <td className="num mono">{run.documents_used}</td>
            <td className="num mono">{run.claims.length}</td>
            <td className="muted table__wide">
              {run.hypotheses[0]?.text ?? run.error ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
