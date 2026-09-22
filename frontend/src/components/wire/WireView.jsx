import { useState } from "react";

import { api } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { usePersistentState } from "../../hooks/usePersistentState";
import WireFeed from "./WireFeed";
import WireGraph from "./WireGraph";
import WireSignals from "./WireSignals";

const WINDOWS = [
  { days: 7, label: "1W" },
  { days: 30, label: "1M" },
  { days: 90, label: "3M" },
  { days: 365, label: "1Y" },
];

/**
 * The news graph of the book: what happened (Feed), how a
 * security is connected and what the model expects next
 * (Graph), and how surprising each day's news was (Signals).
 * Everything is as of the desk's date.
 */
export default function WireView({ ticker, holdings, era, onSelectTicker }) {
  const [tab, setTab] = usePersistentState("wireTab", "feed");
  const [days, setDays] = usePersistentState("wireDays", 30);
  const [scope, setScope] = useState("book");

  const focus = scope === "ticker" ? ticker : null;

  const status = useResource(api.wireStatus, `wire:status:${era}`, { maxAge: 60_000 });
  const feed = useResource(
    () => api.wireFeed({ days, ticker: focus }),
    `wire:feed:${focus ?? "book"}:${days}:${era}`,
    { enabled: tab === "feed", maxAge: 300_000 }
  );
  const graph = useResource(
    () => api.wireGraph(ticker, days),
    `wire:graph:${ticker}:${days}:${era}`,
    { enabled: tab === "graph" && Boolean(ticker), maxAge: 300_000 }
  );
  const signals = useResource(
    () => api.wireSignals(ticker),
    `wire:signals:${ticker}:${era}`,
    { enabled: tab === "signals" && Boolean(ticker), maxAge: 300_000 }
  );

  const counts = status.data;

  return (
    <div className="wire">
      <header className="wire__hero">
        <div>
          <span className="eyebrow">Wire</span>
          <h1>The news graph of the book</h1>
          <p className="muted">
            Every article read once, as timestamped edges between securities, the entities they are
            named with and the events they report. A temporal graph network learns what normally
            comes next; what it did not expect is the signal.
          </p>
        </div>

        <dl className="wire__counts mono">
          <div>
            <dt className="eyebrow">Articles</dt>
            <dd>{counts ? counts.articles.toLocaleString("en-US") : "—"}</dd>
          </div>
          <div>
            <dt className="eyebrow">Edges</dt>
            <dd>{counts ? counts.edges.toLocaleString("en-US") : "—"}</dd>
          </div>
          <div>
            <dt className="eyebrow">Nodes</dt>
            <dd>{counts ? counts.nodes.toLocaleString("en-US") : "—"}</dd>
          </div>
          <div>
            <dt className="eyebrow">Model</dt>
            <dd className={counts?.model_trained ? "up" : "muted"}>
              {counts ? (counts.model_trained ? "trained" : "not trained") : "—"}
            </dd>
          </div>
        </dl>
      </header>

      <div className="wire__bar">
        <nav className="tabs">
          {[
            ["feed", "Feed"],
            ["graph", "Graph"],
            ["signals", "Signals"],
          ].map(([key, label]) => (
            <button key={key} className={`tabs__tab ${tab === key ? "is-active" : ""}`} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </nav>

        <div className="wire__controls">
          {tab === "feed" && (
            <div className="seg">
              <button className={`seg__item ${scope === "book" ? "is-active" : ""}`} onClick={() => setScope("book")}>
                The book
              </button>
              <button className={`seg__item mono ${scope === "ticker" ? "is-active" : ""}`} onClick={() => setScope("ticker")}>
                {ticker}
              </button>
            </div>
          )}
          {tab !== "signals" && (
            <div className="seg">
              {WINDOWS.map((w) => (
                <button key={w.days} className={`seg__item mono ${days === w.days ? "is-active" : ""}`} onClick={() => setDays(w.days)}>
                  {w.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {counts && counts.edges === 0 && (
        <div className="wire__empty">
          <p>
            The graph is empty. On the GPU box: <code>make news ARGS="--since 2025-09-22 --providers finnhub"</code>,
            then <code>make wire-ingest</code>, <code>make wire-train</code>, <code>make wire-score</code>.
          </p>
        </div>
      )}

      {tab === "feed" && (
        <WireFeed rows={feed.data} loading={feed.loading} error={feed.error} onSelectTicker={onSelectTicker} />
      )}
      {tab === "graph" && (
        <WireGraph
          ticker={ticker}
          holdings={holdings}
          graph={graph.data}
          loading={graph.loading}
          error={graph.error}
          onSelectTicker={onSelectTicker}
        />
      )}
      {tab === "signals" && (
        <WireSignals ticker={ticker} holdings={holdings} rows={signals.data} loading={signals.loading} error={signals.error} onSelectTicker={onSelectTicker} />
      )}
    </div>
  );
}
