import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api/client";
import AnomalyTable from "./components/anomalies/AnomalyTable";
import StrategyMarketplace from "./components/anomalies/StrategyMarketplace";
import PriceChart from "./components/chart/PriceChart";
import SpreadChart from "./components/chart/SpreadChart";
import InvestigateView from "./components/investigation/InvestigateView";
import InvestigationPanel from "./components/investigation/InvestigationPanel";
import InvestigationsTable from "./components/investigation/InvestigationsTable";
import SideRail from "./components/layout/SideRail";
import Tabs from "./components/layout/Tabs";
import TickerTape from "./components/layout/TickerTape";
import TopBar from "./components/layout/TopBar";
import NewsFeed from "./components/news/NewsFeed";
import NewsTable from "./components/news/NewsTable";
import PerformanceStrip from "./components/portfolio/PerformanceStrip";
import PortfolioPage from "./components/portfolio/PortfolioPage";
import PositionsTable from "./components/portfolio/PositionsTable";
import DiscoveryView from "./components/stories/DiscoveryView";
import FindingsPanel from "./components/stories/FindingsPanel";
import CopilotStrip from "./components/stories/CopilotStrip";
import HorizonMatrix from "./components/stories/HorizonMatrix";
import MicroscopePanel from "./components/stories/MicroscopePanel";
import { isActive, useInvestigation } from "./hooks/useInvestigation";
import { usePersistentState } from "./hooks/usePersistentState";
import { useResource } from "./hooks/useResource";
import { useTheme } from "./hooks/useTheme";
import { BOTTOM_TABS, SIDE_TABS, resolveTab } from "./lib/deskTabs";
import { resourceCache } from "./lib/resourceCache";

// Chart depth that makes each horizon legible.
const HORIZON_DAYS = { "1d": 45, "1w": 90, "1m": 180, "3m": 365, "1y": 730 };

// Deep link used by the browser extension:
//   /?mode=copilot&ticker=NVDA
const LINK = new URLSearchParams(window.location.search);
const MODES = ["postmortem", "copilot", "discovery"];
const VIEWS = [...MODES, "portfolio", "graph"];

// How long an answer is shown without asking again. News is
// served from the desk's own cache and refreshed behind the
// scenes, so re-entering a feed should never wait.
const MINUTES = 60_000;
const NEWS_AGE = 10 * MINUTES;
const MARKET_AGE = 2 * MINUTES;
const SCAN_AGE = 5 * MINUTES;

const tabLabel = (run) =>
  [run.anomaly.ticker, ...run.anomaly.related_tickers].join("/");
const LINKED = LINK.get("ticker")?.trim() || null;

const RANGES = [
  { key: 30, label: "1M" },
  { key: 90, label: "3M" },
  { key: 180, label: "6M" },
  { key: 365, label: "1Y" },
  { key: 730, label: "2Y" },
  // Everything the desk holds (HISTORY_DAYS, about 4.4 years).
  { key: 2000, label: "ALL" },
];

export default function App() {
  const [theme, toggleTheme] = useTheme();

  // Where the manager was is part of the work: it survives a
  // reload, and a deep link from the extension overrides it.
  const [view, setView] = usePersistentState(
    "view",
    "postmortem",
    (value) => VIEWS.includes(value),
    // /?mode=portfolio and /?mode=graph are links too.
    VIEWS.includes(LINK.get("mode")) ? LINK.get("mode") : undefined
  );

  const [horizon, setHorizon] = usePersistentState("horizon", "1w", (value) =>
    Object.hasOwn(HORIZON_DAYS, value)
  );
  const [chosenTicker, setTicker] = usePersistentState(
    "ticker",
    null,
    undefined,
    // A ticker sent by the extension wins over the remembered one.
    LINKED != null ? null : undefined
  );
  const [days, setDays] = usePersistentState("days", 180);
  const [centerTab, setCenterTab] = usePersistentState("centerTab", "chart");
  const [wantedSideTab, setSideTab] = usePersistentState("sideTab", "findings");
  const [wantedBottomTab, setBottomTab] = usePersistentState(
    "bottomTab",
    LINK.get("mode") === "copilot" ? "peers" : "anomalies"
  );

  // The remembered tab, when the current view has it (lib/deskTabs).
  const sideTab = resolveTab(SIDE_TABS, view, wantedSideTab);
  const bottomTab = resolveTab(BOTTOM_TABS, view, wantedBottomTab);

  const [strategy, setStrategy] = usePersistentState("strategy", null);
  const [anomaly, setAnomaly] = usePersistentState("anomaly", null);
  const [newsDay, setNewsDay] = useState(null);
  const [pair, setPair] = useState(null);
  const [pairScan, setPairScan] = useState(null);

  const [investigationId, setInvestigationId] = usePersistentState("investigation", null);
  const [starting, setStarting] = useState(false);
  const [actionError, setActionError] = useState(null);

  // Which model reads the next anomaly, and which ClaimGraphs
  // are open as tabs in the Why view.
  const [modelId, setModelId] = usePersistentState("model", null);
  const [tabs, setTabs] = usePersistentState("tabs", [], Array.isArray);
  const [activeTab, setActiveTab] = usePersistentState("activeTab", "compare");
  const [examples, setExamples] = useState({});
  const [focusAnomalyId, setFocusAnomalyId] = useState(null);

  // /?mode=graph&open=INV-... opens that ClaimGraph as a tab:
  // a graph can be sent to a colleague as a link.
  useEffect(() => {
    const linked = LINK.get("open");

    if (!linked) return undefined;

    let cancelled = false;

    api
      .investigation(linked)
      .then((run) => {
        if (cancelled) return;

        setTabs((current) =>
          current.some((tab) => tab.id === run.investigation_id)
            ? current
            : [
                ...current,
                {
                  id: run.investigation_id,
                  label: tabLabel(run),
                  model: run.model_label || run.model.split("/").pop(),
                  title: run.anomaly.summary,
                },
              ]
        );
        setActiveTab(run.investigation_id);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [setTabs, setActiveTab]);

  // A view is mounted the first time it is shown, then kept.
  const [visited, setVisited] = useState(() => new Set([view]));

  if (!visited.has(view)) setVisited(new Set([...visited, view]));

  // ---------------------------------------------------
  // Data
  // ---------------------------------------------------

  const system = useResource(api.system, "system", { maxAge: 15_000 });
  const asOf = system.data?.as_of ?? null;

  // Everything computed from the market is keyed by the date
  // the desk believes it is: travelling in time is a different
  // set of answers, not a stale one.
  const era = asOf ?? "live";

  const portfolio = useResource(api.portfolio, `portfolio:${era}`, {
    maxAge: MARKET_AGE,
    persist: true,
  });
  const investigations = useResource(api.investigations, "investigations", {
    maxAge: 20_000,
  });
  const models = useResource(api.models, "models", { maxAge: 15_000 });

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

  const tape = useResource(api.tape, `tape:${book}:${era}`, {
    enabled: hasBook,
    maxAge: MARKET_AGE,
  });
  const bookAnomalies = useResource(() => api.anomalies(), `anomalies:${book}:${era}`, {
    enabled: hasBook,
    maxAge: SCAN_AGE,
    persist: true,
  });
  const bookNews = useResource(api.portfolioNews, `news:book:${book}:${era}`, {
    enabled: hasBook && bottomTab === "news",
    maxAge: NEWS_AGE,
    persist: true,
  });

  const quote = useResource(() => api.quote(ticker), `quote:${ticker}:${era}`, {
    enabled: hasTicker,
    maxAge: MARKET_AGE,
  });
  const copilot = view === "copilot";
  const chartDays = copilot ? HORIZON_DAYS[horizon] : days;

  const candles = useResource(
    () => api.candles(ticker, chartDays),
    `candles:${ticker}:${chartDays}:${era}`,
    { enabled: hasTicker, maxAge: MARKET_AGE }
  );
  const postmortem = useResource(api.postmortem, `postmortem:${book}:${era}`, {
    enabled: hasBook,
    maxAge: SCAN_AGE,
    persist: true,
  });
  const microscope = useResource(
    () => api.microscope(ticker, horizon),
    `microscope:${ticker}:${horizon}:${era}`,
    { enabled: hasTicker && copilot, maxAge: SCAN_AGE }
  );
  const tickerAnomalies = useResource(
    () => api.anomalies(ticker),
    `anomalies:${ticker}:${book}:${era}`,
    { enabled: hasTicker && hasBook, maxAge: SCAN_AGE }
  );
  const strategies = useResource(
    () => api.strategies(ticker),
    `strategies:${ticker}:${book}:${era}`,
    { enabled: hasTicker && hasBook, maxAge: SCAN_AGE }
  );
  const tickerScan = useResource(
    () => api.pairScan(ticker),
    `pairs:${ticker}:${book}:${era}`,
    { enabled: hasTicker && hasBook, maxAge: SCAN_AGE }
  );

  // The wire is remembered across views and reloads: opening
  // the News tab again shows it at once and refreshes behind.
  const tickerNews = useResource(() => api.tickerNews(ticker), `news:${ticker}:${era}`, {
    enabled: hasTicker,
    maxAge: NEWS_AGE,
    persist: true,
  });
  // A session clicked on the chart: the weeks around it are
  // fetched from the providers that keep history, however far
  // back the chart goes.
  const dayNews = useResource(
    () => api.tickerNews(ticker, newsDay),
    `news:${ticker}:${newsDay}:${era}`,
    { enabled: hasTicker && Boolean(newsDay), maxAge: NEWS_AGE, persist: true }
  );
  const newsSources = useResource(api.newsSources, "news-sources", {
    enabled: sideTab === "news",
    maxAge: MINUTES,
  });
  const anomalyNews = useResource(
    () => api.anomalyNews(anomaly.anomaly_id, anomaly.ticker),
    `anomaly-news:${anomaly?.anomaly_id}:${era}`,
    { enabled: anomaly != null, maxAge: NEWS_AGE, persist: true }
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

  const reloadInvestigations = investigations.reload;
  const reloadPostmortem = postmortem.reload;

  const onSettled = useCallback(() => {
    reloadInvestigations();
    reloadPostmortem();
  }, [reloadInvestigations, reloadPostmortem]);

  const [investigation] = useInvestigation(investigationId, onSettled);

  // While anything is being read, the list is what shows its
  // progress in the comparison and in the blotter.
  const anyActive = (investigations.data ?? []).some(isActive);

  useEffect(() => {
    if (!anyActive) return undefined;

    const timer = setInterval(reloadInvestigations, 2500);

    return () => clearInterval(timer);
  }, [anyActive, reloadInvestigations]);

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
  }, [setTicker, setAnomaly, setInvestigationId, setCenterTab, setView]);

  const selectAnomaly = useCallback((selected) => {
    setAnomaly(selected);
    setInvestigationId(null);
    setActionError(null);
    setSideTab("explain");
    setView((current) => (current === "copilot" ? "copilot" : "postmortem"));

    setTicker(selected.ticker);
    setNewsDay(null);

    if (selected.strategy === "pairs") {
      setPair([selected.ticker, selected.related_tickers[0]]);
      setCenterTab("spread");
    } else {
      setPair(null);
      setCenterTab("chart");
    }
  }, [setAnomaly, setInvestigationId, setSideTab, setView, setTicker, setCenterTab]);

  const selectDay = useCallback((day) => {
    setNewsDay(day);
    setSideTab("news");
  }, [setSideTab]);

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

  const explain = useCallback(
    async (target, chosenModel) => {
      const run = await api.startInvestigation(
        target.anomaly_id,
        target.ticker,
        chosenModel ?? undefined
      );

      reloadInvestigations();

      return run;
    },
    [reloadInvestigations]
  );

  const startInvestigation = async (chosenModel) => {
    setStarting(true);
    setActionError(null);

    try {
      const run = await explain(anomaly, chosenModel ?? activeModel?.id);

      setInvestigationId(run.investigation_id);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setStarting(false);
    }
  };

  // One investigation per online model, from the same
  // admissible evidence, then straight to the comparison.
  const startWithEveryModel = async () => {
    setStarting(true);
    setActionError(null);

    const readers = (models.data?.models ?? []).filter(
      (model) => model.online && model.roles.includes("analysis")
    );

    try {
      const runs = await Promise.all(
        readers.map((model) => explain(anomaly, model.id))
      );

      setInvestigationId(runs[0]?.investigation_id ?? null);
      setFocusAnomalyId(anomaly.anomaly_id);
      setActiveTab("compare");
      setView("graph");
    } catch (error) {
      setActionError(error.message);
    } finally {
      setStarting(false);
    }
  };

  const openTab = useCallback(
    (run) => {
      setTabs((current) =>
        current.some((tab) => tab.id === run.investigation_id)
          ? current
          : [
              ...current,
              {
                id: run.investigation_id,
                label: tabLabel(run),
                model: run.model_label || run.model.split("/").pop(),
                title: run.anomaly.summary,
              },
            ]
      );

      setActiveTab(run.investigation_id);
      setView("graph");
    },
    [setTabs, setActiveTab, setView]
  );

  const closeTab = (id) => {
    setTabs((current) => current.filter((tab) => tab.id !== id));
    setExamples((current) =>
      Object.fromEntries(Object.entries(current).filter(([key]) => key !== id))
    );

    if (activeTab === id) setActiveTab("compare");
  };

  const openExample = (run, label) => {
    setExamples((current) => ({ ...current, [run.investigation_id]: run }));

    setTabs((current) =>
      current.some((tab) => tab.id === run.investigation_id)
        ? current
        : [
            ...current,
            { id: run.investigation_id, label: "EXAMPLE", model: label, title: label, example: true },
          ]
    );

    setActiveTab(run.investigation_id);
  };

  const openInvestigation = (run) => {
    setAnomaly(run.anomaly);
    setInvestigationId(run.investigation_id);
    setSideTab("explain");

    if (run.graph) openTab(run);
    else setView("postmortem");
  };

  const timeTravel = async (date) => {
    setActionError(null);

    try {
      await api.timeTravel(date);

      // Another date is another market: nothing selected on
      // the old one can be assumed to exist on the new one.
      setAnomaly(null);
      setNewsDay(null);
      setPair(null);
      setPairScan(null);
      system.reload();
    } catch (error) {
      setActionError(error.message);
    }
  };

  const refreshNews = async () => {
    try {
      await api.refreshNews(ticker);
    } catch (error) {
      setActionError(error.message);
    }

    resourceCache.forget(`news:${ticker}`);
    tickerNews.reload();
    newsSources.reload();
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

  const activeModel = pickModel(models.data, modelId);

  const anomalyRuns = useMemo(
    () =>
      (investigations.data ?? []).filter(
        (run) => run.anomaly.anomaly_id === anomaly?.anomaly_id
      ),
    [investigations.data, anomaly]
  );

  // Example tabs live in memory only: after a reload they are gone.
  const openTabs = tabs
    .filter((tab) => !tab.example || examples[tab.id])
    .map((tab) => (tab.example ? { ...tab, run: examples[tab.id] } : tab));

  const shownTab =
    activeTab === "compare" || openTabs.some((tab) => tab.id === activeTab)
      ? activeTab
      : "compare";

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
        models={models.data}
        modelId={activeModel?.id}
        asOf={asOf}
        latestSession={new Date().toISOString().slice(0, 10)}
        theme={theme}
        onSelectModel={setModelId}
        onTimeTravel={timeTravel}
        onToggleTheme={toggleTheme}
        onSelectTicker={selectTicker}
        onAddTicker={addTicker}
        onRemoveTicker={removeTicker}
      />

      <SideRail
        view={view}
        badges={{ graph: openTabs.length }}
        onChange={(next) => {
          // Moving between Past and Now changes what the side
          // panels mean; coming back from another view does not
          // touch them, so the desk is as it was left.
          if (MODES.includes(next) && MODES.includes(view) && next !== view) {
            setSideTab("findings");
            setBottomTab(next === "copilot" ? "peers" : "anomalies");
            setCenterTab("chart");
          }

          setView(next);
        }}
      />

      {/* Views stay mounted once visited and are hidden, not
          removed: a ClaimGraph, a feed or a discovery scan is
          still there when the manager comes back to it. */}
      {visited.has("graph") && (
        <main className="app__main app__main--full" hidden={view !== "graph"}>
          <InvestigateView
            tabs={openTabs}
            active={shownTab}
            visible={view === "graph"}
            theme={theme}
            investigations={investigations.data}
            models={models.data}
            focusAnomalyId={focusAnomalyId}
            onActivate={setActiveTab}
            onClose={closeTab}
            onOpen={openTab}
            onOpenExample={openExample}
            onExplain={explain}
            onSettled={onSettled}
          />
        </main>
      )}

      {visited.has("discovery") && (
        <main className="app__main app__main--full" hidden={view !== "discovery"}>
          <DiscoveryView
            modelId={activeModel?.id}
            modelLabel={activeModel?.label}
            onReason={selectAnomaly}
          />
        </main>
      )}

      {visited.has("portfolio") && (
        <main className="app__main app__main--full" hidden={view !== "portfolio"}>
          <PortfolioPage
            portfolio={portfolio.data}
            investigations={investigations.data}
            anomalies={bookAnomalies.data}
            asOf={asOf}
            onSelectTicker={selectTicker}
            onSelectAnomaly={selectAnomaly}
            onOpenInvestigation={openInvestigation}
            onPortfolioChanged={portfolio.reload}
          />
        </main>
      )}

      {desk && (
        <>
          <main className="app__main">
            {copilot ? (
              <CopilotStrip
                ticker={ticker}
                microscope={microscope.data}
                horizon={horizon}
                onHorizon={setHorizon}
              />
            ) : (
              <PerformanceStrip portfolio={portfolio.data} asOf={system.data?.as_of} />
            )}

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

              {!copilot && (
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
                  tabs={
                    copilot
                      ? [
                          { key: "peers", label: "Peers × timescales" },
                          {
                            key: "anomalies",
                            label: `Signals on ${ticker ?? ""}`,
                            count: blotter.length,
                          },
                        ]
                      : [
                          { key: "anomalies", label: "Anomalies", count: blotter.length },
                          { key: "positions", label: "Positions" },
                          { key: "news", label: "News" },
                          {
                            key: "investigations",
                            label: "Investigations",
                            count: investigations.data?.length || null,
                          },
                        ]
                  }
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
                {bottomTab === "peers" && (
                  <HorizonMatrix
                    microscope={microscope.data}
                    error={microscope.error}
                    horizon={horizon}
                    onHorizon={setHorizon}
                    onSelectTicker={selectTicker}
                  />
                )}

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
                tabs={
                  copilot
                    ? [
                        { key: "findings", label: "Unusual" },
                        { key: "news", label: "News", count: tickerNews.data?.length },
                        { key: "explain", label: "Explain" },
                      ]
                    : [
                        { key: "findings", label: "Findings" },
                        { key: "monitors", label: "Monitors" },
                        { key: "news", label: "News", count: tickerNews.data?.length },
                        { key: "explain", label: "Explain" },
                      ]
                }
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
                  news={newsDay ? dayNews.data : tickerNews.data}
                  loading={newsDay ? dayNews.loading : tickerNews.loading}
                  refreshing={newsDay ? dayNews.refreshing : tickerNews.refreshing}
                  error={newsDay ? dayNews.error : tickerNews.error}
                  day={newsDay}
                  sources={newsSources.data}
                  onClearDay={() => setNewsDay(null)}
                  onRefresh={refreshNews}
                />
              )}

              {sideTab === "explain" && (
                <InvestigationPanel
                  anomaly={anomaly}
                  finding={finding}
                  anomalyNews={anomalyNews}
                  investigation={investigation}
                  runs={anomalyRuns}
                  llm={llm}
                  models={models.data}
                  modelId={activeModel?.id}
                  starting={starting}
                  error={actionError}
                  onSelectModel={setModelId}
                  onStart={startInvestigation}
                  onStartAll={startWithEveryModel}
                  onOpenRun={(run) => setInvestigationId(run.investigation_id)}
                  onCompare={() => {
                    setFocusAnomalyId(anomaly.anomaly_id);
                    setActiveTab("compare");
                    setView("graph");
                  }}
                  onOpenGraph={() => openTab(investigation)}
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

/*
 * The model in use is always one that answers. A remembered
 * choice that has gone offline (its server was stopped) gives
 * way to the default, or to whichever model is up, and comes
 * back by itself when its server does.
 */
function pickModel(list, chosenId) {
  const readers = (list?.models ?? []).filter((model) =>
    model.roles.includes("analysis")
  );

  const chosen = readers.find((model) => model.id === chosenId);

  if (chosen?.online) return chosen;

  return (
    readers.find((model) => model.default && model.online) ??
    readers.find((model) => model.online) ??
    chosen ??
    readers[0] ??
    null
  );
}

function firstPair(scan) {
  const fit = scan?.fits.find((item) => item.flagged) ?? scan?.fits[0];

  return fit ? [fit.ticker_a, fit.ticker_b] : null;
}
