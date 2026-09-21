// Discovery consumes the existing analytical universe; it never writes research.
export async function discover({asOf, positions = [], signal, request = fetch}) {
  async function read(path, options = {}) {
    const response = await request(path, {...options, signal});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error ?? 'Discovery unavailable');
    return body;
  }
  const scan = await read('/api/anomalies/historical-scan', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({as_of: asOf, entry: 1.5, corr_min: .65, alpha: .05}),
  });
  const held = new Set(positions.map(p => p.ticker));
  const candidates = (scan.candidates ?? []).filter(c =>
    c.ticker_a && c.ticker_b && c.ticker_a !== c.ticker_b &&
    Number.isFinite(c.z_score) && Math.abs(c.z_score) >= 1.5 &&
    Number.isFinite(c.correlation) && c.correlation >= .65 &&
    Number.isFinite(c.cointegration_p) && c.cointegration_p >= 0 && c.cointegration_p <= .05);
  const overlaps = c => held.has(c.ticker_a) || held.has(c.ticker_b);
  candidates.sort((a,b) => Number(overlaps(a))-Number(overlaps(b)) ||
    Math.abs(b.z_score)-Math.abs(a.z_score) || a.pair.localeCompare(b.pair));
  // Exact identity matters: a Yahoo search can return similar, unrelated symbols.
  for (const candidate of candidates) {
    const securities = await Promise.all([candidate.ticker_a,candidate.ticker_b].map(async ticker => {
      const result = await read(`/api/instruments/search?${new URLSearchParams({q:ticker})}`);
      return result.securities.find(s => s.ticker === ticker && s.identity === ticker);
    }));
    if (securities.every(Boolean)) return {scan, candidate: {...candidate,
      requested_as_of: asOf}, securities, alreadyHeld: overlaps(candidate)};
  }
  return {scan, candidate: null};
}
