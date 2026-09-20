import { useCallback, useMemo, useState } from "react";

import { api } from "./api/client";
import AnomalyTable from "./components/anomalies/AnomalyTable";
import StrategyMarketplace from "./components/anomalies/StrategyMarketplace";
import PriceChart from "./components/chart/PriceChart";
import SpreadChart from "./components/chart/SpreadChart";
import GraphView from "./components/investigation/GraphView";
import InvestigationPanel from "./components/investigation/InvestigationPanel";
import InvestigationsTable from "./components/investigation/InvestigationsTable";
import SideRail from "./components/layout/SideRail";
import Tabs from "./components/layout/Tabs";
import TickerTape from "./components/layout/TickerTape";
import TopBar from "./components/layout/TopBar";
import ModelPanel from "./components/model/ModelPanel";
import NewsFeed from "./components/news/NewsFeed";
import NewsTable from "./components/news/NewsTable";
import PerformanceStrip from "./components/portfolio/PerformanceStrip";
import PositionsTable from "./components/portfolio/PositionsTable";
import DiscoveryView from "./components/stories/DiscoveryView";
import FindingsPanel from "./components/stories/FindingsPanel";
import HorizonSlider from "./components/stories/HorizonSlider";
import MicroscopePanel from "./components/stories/MicroscopePanel";
import { useInvestigation } from "./hooks/useInvestigation";
import { useResource } from "./hooks/useResource";
import { useTheme } from "./hooks/useTheme";

// Chart depth that makes each horizon legible.
const HORIZON_DAYS = { "1d": 45, "1w": 90, "1m": 180, "3m": 365, "1y": 730 };

// Deep link used by the browser extension:
//   /?mode=copilot&ticker=NVDA
const LINK = new URLSearchParams(window.location.search);
const MODES = ["postmortem", "copilot", "discovery"];
const LINKED = LINK.get("ticker")?.trim() || null;

const RANGES = [
  { key: 30, label: "1M" },
  { key: 90, label: "3M" },
  { key: 180, label: "6M" },
  { key: 365, label: "1Y" },
];

export default function App() {
  const [theme, toggleTheme] = useTheme();

  const [view, setView] = useState(
    MODES.includes(LINK.get("mode")) ? LINK.get("mode") : "postmortem"
  );
  const [horizon, setHorizon] = useState("1w");
  const [chosenTicker, setTicker] = useState(null);
  const [days, setDays] = useState(180);
  const [centerTab, setCenterTab] = useState("chart");
  const [sideTab, setSideTab] = useState("findings");
  const [bottomTab, setBottomTab] = useState("anomalies");

  const [strategy, setStrategy] = useState(null);
  const [anomaly, setAnomaly] = useState(null);
  const [newsDay, setNewsDay] = useState(null);
  const [pair, setPair] = useState(null);
  const [pairScan, setPairScan] = useState(null);

  const [investigationId, setInvestigationId] = useState(null);
  const [starting, setStarting] = useState(false);
  const [actionError, setActionError] = useState(null);

  // ---------------------------------------------------
  // Data
  // ---------------------------------------------------

  const system = useResource(api.system, "system");
  const portfolio = useResource(api.portfolio, "portfolio");
  const investigations = useResource(api.investigations, "investigations");

  // The extension sends whatever was highlighted, which may be
  // "NVDA" or "Nvidia". Symbol search turns both into a ticker.
  const linked = useResource(() => api.searchInstruments(LINKED), "linked", {
    enabled: LINKED != null,
  });

  // Otherwise the desk opens on the holding that hurt the book most.
  const ticker = useMemo(() => {
    if (chosenTicker) return chosenTicker;

    if (LINKED != null) {
      if (linked.loading) return null;

      return linked.data?.[0]?.ticker ?? LINKED.toUpperCase();
    }

    if (!portfolio.data) return null;

    const worst = [...portfolio.data.positions].sort(
      (a, b) => a.contribution_pct - b.contribution_pct
    )[0];

    return worst?.ticker ?? portfolio.data.benchmark;
  }, [chosenTicker, portfolio.data, linked.loading, linked.data]);

  // Anything computed from the holdings reloads when they change.
  const book = portfolio.data?.positions.map((p) => p.ticker).join() ?? null;
  const hasBook = book != null;
  const hasTicker = ticker != null;

  const tape = useResource(api.tape, `tape:${book}`, { enabled: hasBook });
  const bookAnomalies = useResource(() => api.anomalies(), `anomalies:${book}`, {
    enabled: hasBook,
  });
  const bookNews = useResource(api.portfolioNews, `news:${book}`, {
    enabled: hasBook && bottomTab === "news",
  });

  const quote = useResource(() => api.quote(ticker), `quote:${ticker}`, {
    enabled: hasTicker,
  });
  const copilot = view === "copilot";
  const chartDays = copilot ? HORIZON_DAYS[horizon] : days;

  const candles = useResource(
    () => api.candles(ticker, chartDays),
    `candles:${ticker}:${chartDays}`,
    { enabled: hasTicker }
  );
  const postmortem = useResource(api.postmortem, `postmortem:${book}`, {
    enabled: hasBook,
  });
  const microscope = useResource(
    () => api.microscope(ticker, horizon),
    `microscope:${ticker}:${horizon}`,
    { enabled: hasTicker && copilot }
  );
  const tickerAnomalies = useResource(
    () => api.anomalies(ticker),
    `anomalies:${ticker}:${book}`,
    { enabled: hasTicker && hasBook }
  );
  const strategies = useResource(
    () => api.strategies(ticker),
    `strategies:${ticker}:${book}`,
    { enabled: hasTicker && hasBook }
  );
  const tickerScan = useResource(
    () => api.pairScan(ticker),
    `pairs:${ticker}:${book}`,
    { enabled: hasTicker && hasBook }
  );
  const tickerNews = useResource(() => api.tickerNews(ticker), `news:${ticker}`, {
    enabled: hasTicker,
  });
  const anomalyNews = useResource(
    () => api.anomalyNews(anomaly.anomaly_id, anomaly.ticker),
    `anomaly-news:${anomaly?.anomaly_id}`,
    { enabled: anomaly != null }
  );

  // Without an explicit choice the spread tab shows the
  // most interesting pair of the scan: a broken one first.
  const shownScan = pairScan ?? tickerScan.data;
  const shownPair = pair ?? firstPair(shownScan);

  const spread = useResource(
    () => api.pairSpread(shownPair[0], shownPair[1]),
    `spread:${shownPair?.join("/")}`,
    { enabled: shownPair != null && centerTab === "spread" }
  );

  const investigation = useInvestigation(investigationId, () => {
    investigations.reload();
    postmortem.reload();
  });

  // ---------------------------------------------------
  // Actions
  // ---------------------------------------------------

  const selectTicker = useCallback((symbol) => {
    setTicker(symbol);
    setAnomaly(null);
    setNewsDay(null);
    setPair(null);
    setPairScan(null);
    setInvestigationId(null);
    setCenterTab("chart");
    setView((current) => (MODES.includes(current) && current !== "discovery" ? current : "postmortem"));
  }, []);

  const selectAnomaly = useCallback((selected) => {
    setAnomaly(selected);
    setInvestigationId(null);
    setActionError(null);
    setSideTab("explain");
    setView("postmortem");

    setTicker(selected.ticker);
    setNewsDay(null);

    if (selected.strategy === "pairs") {
      setPair([selected.ticker, selected.related_tickers[0]]);
      setCenterTab("spread");
    } else {
      setPair(null);
      setCenterTab("chart");
    }
  }, []);

  const selectDay = useCallback((day) => {
    setNewsDay(day);
    setSideTab("news");
  }, []);

  const addTicker = async (symbol) => {
    setActionError(null);

    try {
      const result = await api.addPosition(symbol, 100);

      selectTicker(symbol.toUpperCase());
      // Adding a holding triggers the pair scan: show what
      // it found, and the spread if there is one.
      setPairScan(result.pair_scan);
      setSideTab("monitors");
      setStrategy("pairs");

      if (result.pair_scan.fits.length > 0) setCenterTab("spread");
      portfolio.reload();
    } catch (error) {
      setActionError(error.message);
    }
  };

  const removeTicker = async (symbol) => {
    setActionError(null);

    try {
      await api.removePosition(symbol);
      portfolio.reload();
    } catch (error) {
      setActionError(error.message);
    }
  };

  const startInvestigation = async () => {
    setStarting(true);
    setActionError(null);

    try {
      const run = await api.startInvestigation(anomaly.anomaly_id, anomaly.ticker);

      setInvestigationId(run.investigation_id);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setStarting(false);
    }
  };

  const openInvestigation = (run) => {
    setAnomaly(run.anomaly);
    setInvestigationId(run.investigation_id);
    setSideTab("explain");
    setView(run.graph ? "graph" : "postmortem");
  };

  // ---------------------------------------------------
  // Derived
  // ---------------------------------------------------

  const chartAnomalies = useMemo(
    () =>
      (tickerAnomalies.data ?? []).filter(
        (item) => strategy == null || item.strategy === strategy
      ),
    [tickerAnomalies.data, strategy]
  );

  const blotter = useMemo(
    () =>
      ((copilot ? tickerAnomalies.data : bookAnomalies.data) ?? []).filter(
        (item) => strategy == null || item.strategy === strategy
      ),
    [copilot, tickerAnomalies.data, bookAnomalies.data, strategy]
  );

  const llm = system.data?.llm;

  const finding = postmortem.data?.findings.find(
    (item) => item.anomaly.anomaly_id === anomaly?.anomaly_id
  );

  const desk = view === "postmortem" || copilot;

  return (
    <div className="app">
      <TopBar
        ticker={ticker}
        quote={quote.data}
        portfolio={portfolio.data}
        llm={llm}
        theme={theme}
        onToggleTheme={toggleTheme}
        onSelectTicker={selectTicker}
        onAddTicker={addTicker}
        onRemoveTicker={removeTicker}
        onOpenModel={() => setView("model")}
      />

      <SideRail view={view} onChange={setView} />

      {view === "model" && (
        <main className="app__main app__main--full">
          <ModelPanel system={system.data} investigations={investigations.data} />
        </main>
      )}

      {view === "graph" && (
        <main className="app__main app__main--full">
          <GraphView investigation={investigation} theme={theme} />
        </main>
      )}

      {view === "discovery" && (
        <main className="app__main app__main--full">
          <DiscoveryView onReason={selectAnomaly} />
        </main>
      )}

      {desk && (
        <>
          <main className="app__main">
            <PerformanceStrip portfolio={portfolio.data} asOf={system.data?.as_of} />

            {(actionError || portfolio.error || candles.error) && (
              <div className="error-banner">
                {actionError ?? portfolio.error ?? candles.error}
              </div>
            )}

            <div className="toolbar">
              <Tabs
                tabs={[
                  { key: "chart", label: "Chart" },
                  { key: "spread", label: "Pair spread" },
                ]}
                active={centerTab}
                onChange={setCenterTab}
              />

              {centerTab === "chart" && (
                <span className="toolbar__hint">
                  Click any session to read the news that was public that day
                </span>
              )}

              {copilot ? (
                <HorizonSlider
                  ticks={microscope.data?.ticks ?? []}
                  horizon={horizon}
                  onChange={setHorizon}
                />
              ) : (
                <div className="toolbar__ranges mono">
                  {RANGES.map((range) => (
                    <button
                      key={range.key}
                      className={days === range.key ? "is-active" : ""}
                      onClick={() => setDays(range.key)}
                    >
                      {range.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <section className="stage">
              {centerTab === "chart" && (
                <PriceChart
                  series={candles.data}
                  anomalies={chartAnomalies}
                  activeStrategy={strategy}
                  selectedDay={newsDay}
                  selectedAnomalyId={anomaly?.anomaly_id}
                  theme={theme}
                  onSelectDay={selectDay}
                />
              )}

              {centerTab === "spread" &&
                (spread.data ? (
                  <SpreadChart spread={spread.data} theme={theme} />
                ) : (
                  <div className="empty">
                    {spread.error ??
                      (shownPair
                        ? "Loading the spread…"
                        : `${ticker} has no cointegrated partner in the book or the peer universe.`)}
                  </div>
                ))}
            </section>

            <section className="blotter">
              <div className="toolbar">
                <Tabs
                  tabs={[
                    { key: "anomalies", label: "Anomalies", count: blotter.length },
                    { key: "positions", label: "Positions" },
                    { key: "news", label: "News" },
                    {
                      key: "investigations",
                      label: "Investigations",
                      count: investigations.data?.length || null,
                    },
                  ]}
                  active={bottomTab}
                  onChange={setBottomTab}
                />

                {strategy && (
                  <button
                    className="btn btn--ghost btn--small"
                    onClick={() => setStrategy(null)}
                  >
                    {strategy.toUpperCase()} only ✕
                  </button>
                )}
              </div>

              <div className="blotter__body">
                {bottomTab === "anomalies" && (
                  <AnomalyTable
                    anomalies={blotter}
                    selectedId={anomaly?.anomaly_id}
                    onSelect={selectAnomaly}
                  />
                )}

                {bottomTab === "positions" && (
                  <PositionsTable
                    portfolio={portfolio.data}
                    ticker={ticker}
                    onSelect={selectTicker}
                    onRemove={removeTicker}
                  />
                )}

                {bottomTab === "news" && (
                  <NewsTable
                    news={bookNews.data}
                    loading={bookNews.loading}
                    onSelectTicker={selectTicker}
                  />
                )}

                {bottomTab === "investigations" && (
                  <InvestigationsTable
                    investigations={investigations.data}
                    onOpen={openInvestigation}
                  />
                )}
              </div>
            </section>
          </main>

          <aside className="app__side">
            <div className="toolbar">
              <Tabs
                tabs={[
                  copilot
                    ? { key: "findings", label: "Unusual" }
                    : { key: "findings", label: "Findings" },
                  { key: "monitors", label: "Monitors" },
                  { key: "news", label: "News", count: tickerNews.data?.length },
                  { key: "explain", label: "Explain" },
                ]}
                active={sideTab}
                onChange={setSideTab}
              />
            </div>

            <div className="app__side-body">
              {sideTab === "findings" && !copilot && (
                <FindingsPanel
                  postmortem={postmortem.data}
                  selectedId={anomaly?.anomaly_id}
                  onSelect={selectAnomaly}
                />
              )}

              {sideTab === "findings" && copilot && (
                <MicroscopePanel
                  microscope={microscope.data}
                  loading={microscope.loading}
                  error={microscope.error}
                  onExplain={selectAnomaly}
                />
              )}

              {sideTab === "monitors" && (
                <StrategyMarketplace
                  strategies={strategies.data ?? []}
                  active={strategy}
                  pairScan={shownScan}
                  onSelect={setStrategy}
                  onSelectPair={(a, b) => {
                    setPair([a, b]);
                    setCenterTab("spread");
                  }}
                />
              )}

              {sideTab === "news" && (
                <NewsFeed
                  ticker={ticker}
                  news={tickerNews.data}
                  loading={tickerNews.loading}
                  error={tickerNews.error}
                  day={newsDay}
                  onClearDay={() => setNewsDay(null)}
                />
              )}

              {sideTab === "explain" && (
                <InvestigationPanel
                  anomaly={anomaly}
                  finding={finding}
                  anomalyNews={anomalyNews}
                  investigation={investigation}
                  llm={llm}
                  starting={starting}
                  error={actionError}
                  onStart={startInvestigation}
                  onOpenGraph={() => setView("graph")}
                />
              )}
            </div>
          </aside>
        </>
      )}

      <TickerTape quotes={tape.data ?? []} llm={llm} onSelect={selectTicker} />
    </div>
  );
}

function firstPair(scan) {
  const fit = scan?.fits.find((item) => item.flagged) ?? scan?.fits[0];

  return fit ? [fit.ticker_a, fit.ticker_b] : null;
}
