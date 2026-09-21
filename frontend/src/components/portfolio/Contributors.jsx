import { percent } from "../../lib/format";
import { rankContributors } from "../../lib/portfolio";

function Side({ label, rows, direction, onSelectTicker }) {
  return (
    <div className="portfolio-contributors__side">
      <span className="eyebrow">{label}</span>

      {rows.length === 0 && <p className="muted">None in this sample.</p>}

      {rows.map((row) => (
        <button
          key={row.ticker}
          className="portfolio-bar"
          title={`${row.ticker} · ${percent(row.value * 100)} of starting wealth over 20 sessions`}
          onClick={() => onSelectTicker(row.ticker)}
        >
          <span className="mono strong">{row.ticker}</span>
          <span className="portfolio-bar__track">
            <span
              className={`portfolio-bar__fill is-${direction}`}
              style={{ width: `${Math.max(row.share * 100, 1.5)}%` }}
            />
          </span>
          <span className={`mono ${direction}`}>{percent(row.value * 100)}</span>
        </button>
      ))}
    </div>
  );
}

/**
 * Which holdings carried the last twenty sessions. Both
 * sides share one scale, so a bar is comparable across
 * them. Contributions are points of starting wealth: they
 * add up to the book's return and explain no cause.
 */
export default function Contributors({ contributions, onSelectTicker }) {
  const ranked = rankContributors(contributions);

  if (ranked.status === "unavailable") {
    return <p className="portfolio-na">{ranked.reason}</p>;
  }

  return (
    <div className="portfolio-contributors">
      <Side
        label="Largest positive"
        rows={ranked.positive}
        direction="up"
        onSelectTicker={onSelectTicker}
      />
      <Side
        label="Largest negative"
        rows={ranked.negative}
        direction="down"
        onSelectTicker={onSelectTicker}
      />
    </div>
  );
}
