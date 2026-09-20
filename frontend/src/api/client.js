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

  postmortem: () => request("/postmortem"),
  microscope: (ticker, horizon) =>
    request(`/microscope/${encodeURIComponent(ticker)}${query({ horizon })}`),
  discovery: () => request("/discovery"),
  startDiscovery: () => request("/discovery", { method: "POST" }),

  investigations: () => request("/investigations"),
  investigation: (id) => request(`/investigations/${encodeURIComponent(id)}`),
  startInvestigation: (anomalyId, ticker) =>
    request("/investigations", {
      method: "POST",
      body: JSON.stringify({ anomaly_id: anomalyId, ticker }),
    }),
};
