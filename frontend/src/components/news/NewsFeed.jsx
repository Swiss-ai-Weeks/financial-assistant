import { dayOf, shortDate } from "../../lib/format";
import { CloseIcon } from "../icons";
import NewsItem from "./NewsItem";

/**
 * Ticker news, optionally narrowed to the session the
 * manager clicked on the chart.
 */
export default function NewsFeed({ ticker, news, loading, error, day, onClearDay }) {
  const items = day
    ? (news ?? []).filter((item) => dayOf(item.published_at) === day)
    : news ?? [];

  return (
    <div className="feed">
      <div className="feed__header">
        <div>
          <h2>{ticker} news</h2>
          <p className="muted">
            {day
              ? `What was public on ${shortDate(day)}`
              : "Everything published over the review window"}
          </p>
        </div>

        {day && (
          <button className="btn btn--ghost btn--small" onClick={onClearDay}>
            <CloseIcon size={14} /> {shortDate(day)}
          </button>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading && !news && (
        <div className="empty">
          <span className="spinner" /> Loading the wire…
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="empty">
          {day
            ? "Nothing was published about this name that day."
            : "No news found for this name."}
        </div>
      )}

      <div className="feed__list">
        {items.map((item) => (
          <NewsItem key={item.news_id} item={item} />
        ))}
      </div>
    </div>
  );
}
