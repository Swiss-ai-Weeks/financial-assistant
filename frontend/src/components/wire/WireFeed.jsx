import { useState } from "react";

import { dateTime, shortDate } from "../../lib/format";
import { eventColor, eventLabel, surpriseWord } from "../../lib/wire";
import { ExternalIcon } from "../icons";

function Event({ row, onSelectTicker }) {
  const [open, setOpen] = useState(false);
  const word = surpriseWord(row.surprise);

  return (
    <li className={`event ${word ? `event--${word}` : ""}`}>
      <button className="event__row" onClick={() => setOpen(!open)}>
        <span className="event__type" style={{ "--event": eventColor(row.event_type) }}>
          {eventLabel(row.event_type)}
        </span>
        <span className="event__label">{row.label}</span>
        <span className="event__tickers mono">
          {row.tickers.map((t) => (
            <button
              key={t}
              className="event__ticker"
              onClick={(e) => {
                e.stopPropagation();
                onSelectTicker(t);
              }}
            >
              {t}
            </button>
          ))}
        </span>
        <span className={`event__direction event__direction--${row.direction}`}>{row.direction}</span>
        {word && (
          <span className="event__surprise mono" title={`Surprise ${row.surprise.toFixed(2)}: the model did not expect this edge`}>
            {word} · {row.surprise.toFixed(2)}
          </span>
        )}
        <span className="event__count mono">{row.count} {row.count === 1 ? "article" : "articles"}</span>
        <span className="event__when mono">{shortDate(row.last)}</span>
      </button>

      {open && (
        <ul className="event__articles">
          {row.articles.map((a, i) => (
            <li key={i}>
              <a href={a.url} target="_blank" rel="noreferrer">
                {a.title} <ExternalIcon size={12} />
              </a>
              <span className="muted mono">
                {a.ticker} · {a.publisher ?? "—"} · {dateTime(a.published_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function WireFeed({ rows, loading, error, onSelectTicker }) {
  const [type, setType] = useState(null);
  const [onlySurprising, setOnlySurprising] = useState(false);

  if (error) return <div className="error-banner">{error}</div>;
  if (loading && !rows) return <div className="empty"><span className="spinner" /> Reading the graph…</div>;
  if (!rows?.length) return <div className="empty">No events in this window.</div>;

  const types = [...new Set(rows.map((r) => r.event_type))];
  const shown = rows.filter((r) => (!type || r.event_type === type) && (!onlySurprising || surpriseWord(r.surprise)));

  return (
    <>
      <div className="feed__filters">
        <div className="seg seg--wrap">
          <button className={`seg__item ${type === null ? "is-active" : ""}`} onClick={() => setType(null)}>All</button>
          {types.map((t) => (
            <button key={t} className={`seg__item ${type === t ? "is-active" : ""}`} onClick={() => setType(type === t ? null : t)}>
              {eventLabel(t)}
            </button>
          ))}
        </div>
        <label className="feed__toggle">
          <input type="checkbox" checked={onlySurprising} onChange={(e) => setOnlySurprising(e.target.checked)} />
          only what the model did not expect
        </label>
      </div>

      <ol className="events">
        {shown.map((row) => (
          <Event key={row.event} row={row} onSelectTicker={onSelectTicker} />
        ))}
      </ol>
      {shown.length === 0 && <div className="empty">Nothing matches.</div>}
    </>
  );
}
