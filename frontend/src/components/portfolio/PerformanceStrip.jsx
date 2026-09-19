import { percent, shortDate, tone } from "../../lib/format";

/**
 * The reason the manager is here: the book against its
 * benchmark over the period under review.
 */
export default function PerformanceStrip({ portfolio }) {
  if (!portfolio) return null;

  const lagging = portfolio.active_return_pct < 0;

  const detractors = [...portfolio.positions]
    .sort((a, b) => a.contribution_pct - b.contribution_pct)
    .slice(0, 3)
    .filter((position) => position.contribution_pct < 0);

  return (
    <section className="strip">
      <div className="strip__headline">
        <span className="eyebrow">
          {portfolio.name} · {shortDate(portfolio.window.start)} –{" "}
          {shortDate(portfolio.window.end)}
        </span>
        <strong>
          {lagging ? "Underperforming" : "Outperforming"} {portfolio.benchmark} by{" "}
          <span className={`mono ${tone(portfolio.active_return_pct)}`}>
            {percent(Math.abs(portfolio.active_return_pct)).replace("+", "")}
          </span>
        </strong>
      </div>

      <div className="strip__figure">
        <span className="eyebrow">Book</span>
        <span className={`mono ${tone(portfolio.month_return_pct)}`}>
          {percent(portfolio.month_return_pct)}
        </span>
      </div>

      <div className="strip__figure">
        <span className="eyebrow">{portfolio.benchmark}</span>
        <span className={`mono ${tone(portfolio.benchmark_return_pct)}`}>
          {percent(portfolio.benchmark_return_pct)}
        </span>
      </div>

      <div className="strip__figure strip__figure--wide">
        <span className="eyebrow">Largest detractors</span>
        <span className="mono">
          {detractors.map((position) => (
            <span key={position.ticker} className="strip__detractor">
              {position.ticker}{" "}
              <span className="down">{percent(position.contribution_pct)}</span>
            </span>
          ))}
        </span>
      </div>
    </section>
  );
}
