import { percent, tone } from "../../lib/format";
import { latestAnomaly, researchStatus } from "../../lib/portfolio";
import MetricValue from "./MetricValue";

const HORIZONS = [1, 5, 20, 63];

function Research({ research }) {
  return (
    <span className={`portfolio-research is-${research.status}`}>
      {research.status === "running" && <span className="spinner" />}
      {research.label}
      {research.open > 0 && <span className="mono"> · {research.open}</span>}
    </span>
  );
}

/**
 * The holdings, each with what was calculated about it and
 * what was researched about it. The two never mix: a return
 * comes from the analysis, a status from the investigations
 * whose anomaly involves the holding.
 */
export default function HoldingsTable({
  portfolio,
  analysis,
  investigations,
  anomalies,
  onSelectTicker,
  onSelectAnomaly,
  onOpenInvestigation,
}) {
  if (!portfolio.positions.length) {
    return (
      <div className="empty">
        The book is empty. State it as weights below, or load the sample.
      </div>
    );
  }

  const rows = [...portfolio.positions].sort((a, b) => b.weight_pct - a.weight_pct);
  const contributions = analysis?.contributions_20;

  return (
    <div className="portfolio__scroll">
      <table className="table portfolio-holdings">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Name</th>
            <th className="num">Weight</th>
            {HORIZONS.map((sessions) => (
              <th key={sessions} className="num">
                {sessions}D
              </th>
            ))}
            <th className="num">Vol 20D</th>
            <th className="num">Contrib 20D</th>
            <th className="num">Anomalies</th>
            <th>Research</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((position) => {
            const security = analysis?.securities?.[position.ticker];

            // A security without prices has one reason for
            // every horizon; pass it down as the metric.
            const missing = security?.status === "unavailable" ? security : null;

            const contribution = contributions?.[position.ticker];
            const anomaly = latestAnomaly(anomalies, position.ticker);
            const research = researchStatus(investigations, position.ticker);

            return (
              <tr key={position.ticker}>
                <td className="mono strong">{position.ticker}</td>
                <td className="muted portfolio-holdings__name">{position.name}</td>
                <td className="num mono">{position.weight_pct.toFixed(1)}%</td>

                {HORIZONS.map((sessions) => (
                  <td key={sessions} className="num">
                    <MetricValue metric={missing ?? security?.[`return_${sessions}`]} compact />
                  </td>
                ))}

                <td className="num">
                  <MetricValue
                    metric={missing ?? security?.volatility_20}
                    toned={false}
                    plain
                    compact
                  />
                </td>

                <td className={`num mono ${tone(contribution)}`}>
                  {Number.isFinite(contribution) ? (
                    percent(contribution * 100)
                  ) : (
                    <span className="portfolio-na" title={contributions?.reason}>
                      —
                    </span>
                  )}
                </td>

                <td className="num mono">
                  {anomaly ? (
                    <button
                      className="portfolio-holdings__anomalies"
                      title={`Explain the latest: ${anomaly.summary}`}
                      onClick={() => onSelectAnomaly(anomaly)}
                    >
                      {position.anomaly_count || 1}
                    </button>
                  ) : (
                    <span className="muted">{position.anomaly_count ?? 0}</span>
                  )}
                </td>

                <td>
                  <Research research={research} />
                </td>

                <td className="num portfolio-holdings__actions">
                  <button
                    className="btn btn--ghost btn--small"
                    onClick={() => onSelectTicker(position.ticker)}
                  >
                    Market
                  </button>

                  {research.run && (
                    <button
                      className="btn btn--ghost btn--small"
                      onClick={() => onOpenInvestigation(research.run)}
                    >
                      Open graph
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
