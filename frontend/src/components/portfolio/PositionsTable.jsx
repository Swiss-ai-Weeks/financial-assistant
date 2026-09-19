import { money, percent, price, tone } from "../../lib/format";
import { CloseIcon } from "../icons";

export default function PositionsTable({ portfolio, ticker, onSelect, onRemove }) {
  if (!portfolio?.positions.length) {
    return (
      <div className="empty">
        The book is empty. Search a ticker in the top bar and add it.
      </div>
    );
  }

  const rows = [...portfolio.positions].sort(
    (a, b) => a.contribution_pct - b.contribution_pct
  );

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Name</th>
          <th className="num">Shares</th>
          <th className="num">Last</th>
          <th className="num">MV ($)</th>
          <th className="num">Weight</th>
          <th className="num">1D</th>
          <th className="num">1M</th>
          <th className="num">Contribution</th>
          <th className="num">Anomalies</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((position) => (
          <tr
            key={position.ticker}
            className={position.ticker === ticker ? "is-selected" : ""}
            onClick={() => onSelect(position.ticker)}
          >
            <td className="mono strong">{position.ticker}</td>
            <td className="muted">{position.name}</td>
            <td className="num mono">{money(position.shares)}</td>
            <td className="num mono">{price(position.last)}</td>
            <td className="num mono">{money(position.market_value)}</td>
            <td className="num mono">{position.weight_pct.toFixed(1)}%</td>
            <td className={`num mono ${tone(position.day_change_pct)}`}>
              {percent(position.day_change_pct)}
            </td>
            <td className={`num mono ${tone(position.month_return_pct)}`}>
              {percent(position.month_return_pct)}
            </td>
            <td className={`num mono ${tone(position.contribution_pct)}`}>
              {percent(position.contribution_pct)}
            </td>
            <td className="num mono">{position.anomaly_count}</td>
            <td className="num">
              <button
                className="table__action"
                title={`Remove ${position.ticker}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onRemove(position.ticker);
                }}
              >
                <CloseIcon size={16} />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
