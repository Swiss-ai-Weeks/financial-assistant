// Resolved against the page, not the host root: behind a
// forwarding prefix (/proxy/8081/) "/api" would leave the
// prefix and hit the proxy itself, which answers 404.
const BASE =
  import.meta.env.VITE_API_URL ??
  new URL("api", document.baseURI).href.replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);

    throw new Error(body?.detail ?? `Request failed (HTTP ${response.status})`);
  }

  return response.json();
}

function query(params) {
  const entries = Object.entries(params).filter(([, value]) => value != null);

  return entries.length ? `?${new URLSearchParams(entries)}` : "";
}

export const api = {
  system: () => request("/system"),

  // Move the whole desk to a past session; null returns to today.
  timeTravel: (asOf) =>
    request("/system/as-of", {
      method: "PUT",
      body: JSON.stringify({ as_of: asOf }),
    }),

  portfolio: () => request("/portfolio"),
  addPosition: (ticker, shares) =>
    request("/portfolio/positions", {
      method: "POST",
      body: JSON.stringify({ ticker, shares }),
    }),
  removePosition: (ticker) =>
    request(`/portfolio/positions/${encodeURIComponent(ticker)}`, {
      method: "DELETE",
    }),
  resetPortfolio: () => request("/portfolio/reset", { method: "POST" }),

  // The book stated as weights, and the calculations on it.
  setWeights: (positions, { name, notional } = {}) =>
    request("/portfolio/weights", {
      method: "PUT",
      body: JSON.stringify({ positions, name, notional }),
    }),
  portfolioAnalysis: () => request("/portfolio/analysis"),
  simulateOverlay: (tickerA, tickerB, grossOverlay = 0.02, lookback = 252) =>
    request("/portfolio/simulate", {
      method: "POST",
      body: JSON.stringify({
        ticker_a: tickerA,
        ticker_b: tickerB,
        gross_overlay: grossOverlay,
        lookback,
      }),
    }),
  marketContext: (tickers) =>
    request("/portfolio/market", {
      method: "POST",
      body: JSON.stringify({ tickers }),
    }),

  searchInstruments: (q) => request(`/instruments/search${query({ q })}`),
  tape: () => request("/market/tape"),
  quote: (ticker) => request(`/market/${encodeURIComponent(ticker)}/quote`),
  candles: (ticker, days) =>
    request(`/market/${encodeURIComponent(ticker)}/candles${query({ days })}`),

  anomalies: (ticker) => request(`/anomalies${query({ ticker })}`),
  strategies: (ticker) => request(`/strategies${query({ ticker })}`),
  pairScan: (ticker) => request(`/pairs${query({ ticker })}`),
  pairSpread: (a, b) =>
    request(`/pairs/${encodeURIComponent(a)}/${encodeURIComponent(b)}/spread`),

  portfolioNews: () => request("/news"),
  tickerNews: (ticker) =>
    request(`/news/${encodeURIComponent(ticker)}${query({ limit: 200 })}`),
  anomalyNews: (anomalyId, ticker) =>
    request(`/news/anomaly/${encodeURIComponent(anomalyId)}${query({ ticker })}`),
  newsSources: () => request("/news/sources"),
  refreshNews: (ticker) =>
    request(`/news/${encodeURIComponent(ticker)}/refresh${query({ limit: 200 })}`, {
      method: "POST",
    }),

  postmortem: () => request("/postmortem"),
  microscope: (ticker, horizon) =>
    request(`/microscope/${encodeURIComponent(ticker)}${query({ horizon })}`),
  discovery: () => request("/discovery"),
  // The candidates are read by the model chosen on the desk.
  startDiscovery: (modelId) =>
    request("/discovery", {
      method: "POST",
      body: JSON.stringify({ model_id: modelId ?? null }),
    }),

  investigations: () => request("/investigations"),
  investigation: (id) => request(`/investigations/${encodeURIComponent(id)}`),
  startInvestigation: (anomalyId, ticker, modelId) =>
    request("/investigations", {
      method: "POST",
      body: JSON.stringify({ anomaly_id: anomalyId, ticker, model_id: modelId }),
    }),

  // Every configured model (Nemotron, Apertus, ...) and whether it answers.
  models: () => request("/investigations/models"),

  // One bounded research cycle on one open question of a graph.
  startFollowUp: (investigationId, requirementId, modelId) =>
    request(`/investigations/${encodeURIComponent(investigationId)}/followups`, {
      method: "POST",
      body: JSON.stringify({ requirement_id: requirementId, model_id: modelId }),
    }),

  // Commentary on a ClaimGraph view, plus at most one UI action.
  copilot: (payload, signal) =>
    request("/copilot", { method: "POST", body: JSON.stringify(payload), signal }),
};
