import { shortDate, signed } from "../../lib/format";
import { KIND_LABEL, STRATEGY_STYLE } from "../../lib/strategies";

export default function AnomalyTable({ anomalies, selectedId, onSelect }) {
  if (!anomalies.length) {
    return (
      <div className="empty">
        No strategy assumption broke in the review window for this selection.
      </div>
    );
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Market</th>
          <th>Monitor</th>
          <th>Signal</th>
          <th className="num">Z</th>
          <th>Severity</th>
          <th>What happened</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {anomalies.map((anomaly) => (
          <tr
            key={anomaly.anomaly_id}
            className={anomaly.anomaly_id === selectedId ? "is-selected" : ""}
            onClick={() => onSelect(anomaly)}
          >
            <td className="mono">{shortDate(anomaly.observed_on)}</td>
            <td className="mono strong">
              {[anomaly.ticker, ...anomaly.related_tickers].join(" / ")}
            </td>
            <td>
              <span className={`chip chip--${anomaly.strategy}`}>
                {STRATEGY_STYLE[anomaly.strategy].label}
              </span>
            </td>
            <td>{KIND_LABEL[anomaly.kind] ?? anomaly.kind}</td>
            <td className="num mono">{signed(anomaly.z_score)}</td>
            <td>
              <div className="meter" title={`${Math.round(anomaly.severity * 100)}%`}>
                <div
                  className="meter__fill"
                  style={{
                    width: `${anomaly.severity * 100}%`,
                    background: `var(${STRATEGY_STYLE[anomaly.strategy].color})`,
                  }}
                />
              </div>
            </td>
            <td className="muted table__wide">{anomaly.summary}</td>
            <td className="num">
              <span className="table__link">Explain →</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
