import { api } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { money, percent, tone } from "../../lib/format";
import { bookKey } from "../../lib/portfolio";
import Contributors from "./Contributors";
import HoldingsTable from "./HoldingsTable";
import MetricTiles from "./MetricTiles";
import OverlaySimulation from "./OverlaySimulation";
import WeightsEditor from "./WeightsEditor";

const ANALYSIS_MAX_AGE = 5 * 60_000;

function Section({ eyebrow, title, aside, children }) {
  return (
    <section className="portfolio__section">
      <header className="portfolio__section-head">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

function Figure({ label, children }) {
  return (
    <div className="portfolio__figure">
      <span className="eyebrow">{label}</span>
      {children}
    </div>
  );
}

function Header({ portfolio, asOf }) {
  if (!portfolio) {
    return (
      <header className="portfolio__header">
        <div className="portfolio__title">
          <span className="eyebrow">Portfolio · Analytical workspace</span>
          <h1 className="muted">Loading the book…</h1>
        </div>
      </header>
    );
  }

  const count = portfolio.positions.length;

  return (
    <header className="portfolio__header">
      <div className="portfolio__title">
        <span className="eyebrow">Portfolio · Analytical workspace</span>
        <h1>{portfolio.name}</h1>
        <p className="muted">
          <span className="mono">{count}</span> {count === 1 ? "position" : "positions"} · as
          of <span className="mono">{portfolio.window.end}</span>
          {portfolio.manager && <> · {portfolio.manager}</>}
          {asOf && (
            <span className="chip portfolio__replay" title={`The desk is replaying ${asOf}`}>
              Replay
            </span>
          )}
        </p>
      </div>

      <div className="portfolio__figures">
        <Figure label="Market value">
          <span className="mono">${money(portfolio.market_value)}</span>
        </Figure>

        <Figure label={`Book · ${portfolio.window.days}d`}>
          <span className={`mono ${tone(portfolio.month_return_pct)}`}>
            {percent(portfolio.month_return_pct)}
          </span>
        </Figure>

        <Figure label={`Benchmark · ${portfolio.benchmark}`}>
          <span className={`mono ${tone(portfolio.benchmark_return_pct)}`}>
            {percent(portfolio.benchmark_return_pct)}
          </span>
        </Figure>

        <Figure label="Active return">
          <span className={`mono ${tone(portfolio.active_return_pct)}`}>
            {percent(portfolio.active_return_pct)}
          </span>
        </Figure>
      </div>
    </header>
  );
}

/**
 * The book as an object of analysis rather than a blotter:
 * what it did, which holdings did it, what is known about
 * each of them, and what a candidate pair would have changed.
 *
 * Every number is calculated by the server on cached closes
 * at the desk's cutoff; nothing on this page is a forecast.
 */
export default function PortfolioPage({
  portfolio,
  investigations,
  anomalies,
  asOf,
  onSelectTicker,
  onSelectAnomaly,
  onOpenInvestigation,
  onPortfolioChanged,
}) {
  const bookId = bookKey(portfolio);

  // Keyed on the book itself: a revisit opens at once, and a
  // changed weight or replay date is a different calculation.
  const analysis = useResource(
    api.portfolioAnalysis,
    `portfolio-analysis:${bookId}:${asOf ?? "live"}`,
    { enabled: portfolio != null, maxAge: ANALYSIS_MAX_AGE, persist: true }
  );

  const available = analysis.data?.status === "available" ? analysis.data : null;
  const provenance = available?.provenance;

  const saved = ({ sameWeights }) => {
    onPortfolioChanged();

    // New weights arrive as a new key, which recalculates by
    // itself. Reloading now would file the new book's numbers
    // under the old book's key; only a save that kept the
    // weights (a rename, a notional) reloads in place.
    if (sameWeights) analysis.reload();
  };

  return (
    <div className="portfolio">
      <Header portfolio={portfolio} asOf={asOf} />

      <Section
        eyebrow="Deterministic analysis"
        title="What the book did"
        aside={
          <button
            className="btn btn--ghost btn--small"
            disabled={!portfolio || analysis.refreshing}
            onClick={analysis.reload}
          >
            {analysis.refreshing && <span className="spinner" />}
            {analysis.refreshing ? "Calculating…" : "Recalculate"}
          </button>
        }
      >
        {analysis.error && <div className="error-banner">{analysis.error}</div>}

        {!analysis.error && !analysis.data && (
          <div className="empty">
            <span className="spinner" /> Calculating returns, risk and concentration…
          </div>
        )}

        {analysis.data && !available && (
          <p className="portfolio-na portfolio__unavailable">
            Analysis unavailable: {analysis.data.reason ?? "no reason given"}
          </p>
        )}

        {available && (
          <>
            <MetricTiles analysis={available} />

            {provenance && (
              <p className="portfolio__provenance muted mono">
                {provenance.formula_version} · {provenance.source} {provenance.price_field} ·
                cutoff {provenance.as_of_cutoff} · sha256{" "}
                {provenance.input_sha256?.slice(0, 12)}…
              </p>
            )}
          </>
        )}
      </Section>

      {available && (
        <Section eyebrow="Last 20 sessions" title="Contributors">
          <Contributors
            contributions={available.contributions_20}
            onSelectTicker={onSelectTicker}
          />
        </Section>
      )}

      <Section
        eyebrow="Calculated and researched"
        title="Holdings"
        aside={
          <span className="muted portfolio__aside">
            Research status comes from the investigations involving each holding.
          </span>
        }
      >
        {portfolio ? (
          <HoldingsTable
            portfolio={portfolio}
            analysis={available}
            investigations={investigations}
            anomalies={anomalies}
            onSelectTicker={onSelectTicker}
            onSelectAnomaly={onSelectAnomaly}
            onOpenInvestigation={onOpenInvestigation}
          />
        ) : (
          <div className="empty">
            <span className="spinner" /> Loading the holdings…
          </div>
        )}

        <WeightsEditor portfolio={portfolio} onSaved={saved} />
      </Section>

      <Section eyebrow="Historical scenario" title="Simulate a pair overlay">
        <OverlaySimulation
          portfolio={portfolio}
          anomalies={anomalies}
          bookId={bookId}
          asOf={asOf}
        />
      </Section>
    </div>
  );
}
