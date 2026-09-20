import { dateTime, shortDate } from "../../lib/format";
import { KIND_LABEL, STRATEGY_STYLE } from "../../lib/strategies";
import { BoltIcon, GraphIcon } from "../icons";
import NewsItem from "../news/NewsItem";
import FindingFacts from "../stories/FindingFacts";
import ClaimList from "./ClaimList";
import StageList from "./StageList";
import Verdicts from "./Verdicts";

/**
 * One anomaly, read against the news.
 *
 * Headlines published before the evidence cutoff may
 * explain the anomaly. Later ones are shown, dimmed, as
 * hindsight: useful to the reader, inadmissible as cause.
 */
export default function InvestigationPanel({
  anomaly,
  finding,
  anomalyNews,
  investigation,
  llm,
  starting,
  error,
  onStart,
  onOpenGraph,
}) {
  if (!anomaly) {
    return (
      <div className="empty">
        Select an anomaly in the blotter or on the chart. The desk will line up
        the news that was public when it happened and ask Nemotron to explain it.
      </div>
    );
  }

  const running = ["queued", "running"].includes(investigation?.status);
  const news = anomalyNews.data;

  return (
    <div className="explain">
      <header className="explain__header">
        <div className="explain__chips">
          <span className={`chip chip--${anomaly.strategy}`}>
            {STRATEGY_STYLE[anomaly.strategy].label}
          </span>
          <span className="chip">{KIND_LABEL[anomaly.kind] ?? anomaly.kind}</span>
          <span className="chip">{shortDate(anomaly.observed_on)}</span>
        </div>
        <h2>{[anomaly.ticker, ...anomaly.related_tickers].join(" / ")}</h2>
        <p>{finding?.statement ?? anomaly.summary}</p>
      </header>

      <FindingFacts finding={finding} />

      <button
        className="btn btn--block"
        disabled={running || starting || !llm?.online || !news?.admissible.length}
        onClick={onStart}
      >
        <BoltIcon size={16} />
        {running || starting
          ? "Nemotron is reading…"
          : investigation
            ? "Explain again"
            : "Explain with Nemotron"}
      </button>

      {!llm?.online && (
        <p className="explain__note">
          The model is offline ({llm?.detail}). Start it with{" "}
          <code>make llm</code>, or set <code>LLM_BASE_URL</code> in <code>.env</code>.
        </p>
      )}

      {error && <div className="error-banner">{error}</div>}

      {investigation && (
        <section className="explain__section">
          <div className="explain__section-head">
            <span className="eyebrow">Investigation · {investigation.model.split("/").pop()}</span>
            {investigation.graph && (
              <button className="btn btn--ghost btn--small" onClick={onOpenGraph}>
                <GraphIcon size={14} /> Open ClaimGraph
              </button>
            )}
          </div>

          <StageList stages={investigation.stages} />

          {investigation.error && (
            <div className="error-banner">{investigation.error}</div>
          )}
        </section>
      )}

      {investigation?.hypotheses.length > 0 && (
        <section className="explain__section">
          <span className="eyebrow">Why it happened</span>
          <Verdicts hypotheses={investigation.hypotheses} />
        </section>
      )}

      {investigation?.claims.length > 0 && (
        <section className="explain__section">
          <span className="eyebrow">
            Evidence · {investigation.claims.length} claims from{" "}
            {investigation.documents_used} articles
          </span>
          <ClaimList claims={investigation.claims} />
        </section>
      )}

      <section className="explain__section">
        <div className="explain__section-head">
          <span className="eyebrow">
            Admissible news · {news?.admissible.length ?? "…"} · most relevant first
          </span>
          {news && (
            <span className="muted mono">cutoff {dateTime(news.cutoff)} UTC</span>
          )}
        </div>

        {anomalyNews.error && <div className="error-banner">{anomalyNews.error}</div>}

        {news?.admissible.length === 0 && (
          <div className="empty">Nothing was published before this anomaly.</div>
        )}

        <div className="feed__list">
          {news?.admissible.slice(0, 12).map((item) => (
            <NewsItem key={item.news_id} item={item} />
          ))}
        </div>
      </section>

      {news?.hindsight.length > 0 && (
        <section className="explain__section">
          <span className="eyebrow">
            Hindsight · published after the anomaly, never used as evidence
          </span>
          <div className="feed__list">
            {news.hindsight.slice(0, 5).map((item) => (
              <NewsItem key={item.news_id} item={item} dimmed />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
