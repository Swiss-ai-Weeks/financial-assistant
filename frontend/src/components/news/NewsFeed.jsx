import { dayOf, shortDate } from "../../lib/format";
import { CloseIcon, RefreshIcon } from "../icons";
import NewsItem from "./NewsItem";

/**
 * Ticker news, optionally narrowed to the session the
 * manager clicked on the chart.
 */
export default function NewsFeed({
  ticker,
  news,
  loading,
  refreshing,
  error,
  day,
  sources,
  onClearDay,
  onRefresh,
}) {
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

        <div className="feed__actions">
          {day && (
            <button className="btn btn--ghost btn--small" onClick={onClearDay}>
              <CloseIcon size={14} /> {shortDate(day)}
            </button>
          )}

          {onRefresh && (
            <button
              className="btn btn--ghost btn--small"
              disabled={refreshing}
              title="Ask every configured provider again, within its daily budget"
              onClick={onRefresh}
            >
              <RefreshIcon size={14} /> {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          )}
        </div>
      </div>

      <NewsSources sources={sources} />

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

/**
 * Where the wire comes from. The feed is served from the
 * desk's own cache, so it is on screen at once; providers are
 * asked again in the background, each within its free-tier
 * budget. A provider without a key is listed, greyed out.
 */
function NewsSources({ sources }) {
  if (!sources?.length) return null;

  return (
    <div className="feed__sources">
      {sources.map((source) => (
        <span
          key={source.name}
          className={`feed__source mono ${source.configured ? "" : "is-off"} ${
            source.last_error ? "is-failing" : ""
          }`}
          title={
            !source.configured
              ? "No API key configured"
              : [
                  `${source.articles} articles cached`,
                  source.daily_budget != null &&
                    `${source.requests_today}/${source.daily_budget} requests today`,
                  source.last_error && `last error: ${source.last_error}`,
                ]
                  .filter(Boolean)
                  .join(" · ")
          }
        >
          {source.name}
          {source.configured && source.articles > 0 && <small>{source.articles}</small>}
        </span>
      ))}
    </div>
  );
}
