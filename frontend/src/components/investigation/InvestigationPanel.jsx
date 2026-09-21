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
  runs = [],
  llm,
  models,
  modelId,
  starting,
  error,
  onSelectModel,
  onStart,
  onStartAll,
  onOpenRun,
  onCompare,
  onOpenGraph,
}) {
  if (!anomaly) {
    return (
      <div className="empty">
        Select an anomaly in the blotter or on the chart. The desk will line up
        the news and SEC filings that were public when it happened and ask a
        model to explain it.
      </div>
    );
  }

  const running = ["queued", "running"].includes(investigation?.status);
  const news = anomalyNews.data;

  const readers = (models?.models ?? []).filter((model) =>
    model.roles.includes("analysis")
  );

  const reader = readers.find((model) => model.id === modelId) ?? readers[0];
  const readerName = reader?.label ?? "the model";
  const online = reader ? reader.online : llm?.online;

  // A second reading of the same anomaly is a comparison.
  const others = readers.filter(
    (model) => model.online && !runs.some((run) => run.model_id === model.id)
  );

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

      {readers.length > 1 && (
        <div className="explain__readers">
          <span className="eyebrow">Read by</span>

          {readers.map((model) => (
            <button
              key={model.id}
              className={`reader ${model.id === reader?.id ? "is-active" : ""}`}
              title={`${model.model} · ${model.local ? "local" : "external"} · ${model.detail}`}
              onClick={() => onSelectModel(model.id)}
            >
              <span className={`dot ${model.online ? "dot--on" : "dot--off"}`} />
              {model.label}
              <small>{model.local ? "local" : "external"}</small>
            </button>
          ))}
        </div>
      )}

      <button
        className="btn btn--block"
        disabled={running || starting || !online || !news?.admissible.length}
        onClick={() => onStart(reader?.id)}
      >
        <BoltIcon size={16} />
        {running || starting
          ? `${readerName} is reading…`
          : runs.some((run) => run.model_id === reader?.id)
            ? `Explain again with ${readerName}`
            : `Explain with ${readerName}`}
      </button>

      {others.length > 0 && readers.length > 1 && runs.length === 0 && (
        <button
          className="btn btn--ghost btn--block"
          disabled={running || starting || !news?.admissible.length}
          title="One investigation per online model, from the same admissible evidence"
          onClick={onStartAll}
        >
          Explain with every model and compare
        </button>
      )}

      {!online && (
        <p className="explain__note">
          {readerName} is offline ({reader?.detail ?? llm?.detail}). Start it with{" "}
          <code>make llm</code> or <code>make apertus</code>, or pick another
          model above.
        </p>
      )}

      {runs.length > 0 && (
        <section className="explain__section">
          <div className="explain__section-head">
            <span className="eyebrow">Readings of this anomaly · {runs.length}</span>
            {runs.length > 1 && (
              <button className="btn btn--ghost btn--small" onClick={onCompare}>
                Compare
              </button>
            )}
          </div>

          <div className="readings">
            {runs.map((run) => (
              <button
                key={run.investigation_id}
                className={`readings__row ${
                  run.investigation_id === investigation?.investigation_id ? "is-active" : ""
                }`}
                onClick={() => onOpenRun(run)}
              >
                <strong>{run.model_label || run.model.split("/").pop()}</strong>
                <span className={`mono status status--${run.status}`}>{run.status}</span>
                <span className="muted readings__best">
                  {run.hypotheses[0]?.text ?? run.error ?? "…"}
                </span>
              </button>
            ))}
          </div>

          {others.length > 0 && runs.length > 0 && (
            <p className="explain__note">
              Not read yet by {others.map((model) => model.label).join(", ")}: pick it
              above and explain again to compare.
            </p>
          )}
        </section>
      )}

      {error && <div className="error-banner">{error}</div>}

      {investigation && (
        <section className="explain__section">
          <div className="explain__section-head">
            <span className="eyebrow">
              Investigation · {investigation.model_label || investigation.model.split("/").pop()}
            </span>
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

      {investigation?.fundamentals?.length > 0 && (
        <section className="explain__section">
          <span className="eyebrow">SEC fundamentals · as filed by the cutoff</span>
          <div className="fundamentals">
            {investigation.fundamentals.map((item) => (
              <div key={item.ticker} className="fundamentals__row">
                <strong className="mono">{item.ticker}</strong>
                {item.status === "available" ? (
                  <span className="mono">
                    {item.quarters} quarters · {item.calculations} metrics
                    {item.latest_period && ` · to ${shortDate(item.latest_period)}`}
                  </span>
                ) : (
                  <span className="muted">{item.warnings[0] ?? "unavailable"}</span>
                )}
              </div>
            ))}
          </div>
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
            Admissible news · {news?.admissible.length ?? "…"}
          </span>
          {news && (
            <span className="muted mono">cutoff {dateTime(news.cutoff)} UTC</span>
          )}
        </div>

        {news?.key_dates.length > 0 && (
          <p className="explain__keydates">
            Read around{" "}
            {news.key_dates.map((key, index) => (
              <span key={key.day}>
                {index > 0 && ", "}
                the <strong>{key.label}</strong> ({shortDate(key.day)})
              </span>
            ))}
            : what caused a divergence is dated near where it began and peaked,
            not where it was noticed.
          </p>
        )}

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
