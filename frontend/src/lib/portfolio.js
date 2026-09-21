/*
 * The rules of the Portfolio page, kept away from React so
 * they run under node --test: what a valid book of weights
 * is, what the research on a holding amounts to, and which
 * holdings carried the last twenty sessions.
 */

export const NOTICE =
  "Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.";

// A fictional allocation, not a suggestion: both names are
// in the mapped universe, so every calculation has prices.
export const SAMPLE_PORTFOLIO = {
  name: "Sample research portfolio (fictional allocation)",
  positions: [
    { ticker: "COHU", weight: 0.5 },
    { ticker: "PDFS", weight: 0.5 },
  ],
};

export const DEFAULT_NOTIONAL = 1_000_000;

const WEIGHTS_MESSAGE =
  "Use unique tickers and nonnegative decimal weights summing to 1.";

const TICKER = /^[A-Z0-9.^=-]+$/;

/**
 * "One ticker and decimal weight per line" → positions.
 *
 * The same rule the server applies, checked first so a typo
 * costs no round trip: unique tickers, finite non-negative
 * weights, a total within 0.001 of 1.
 */
export function validatePositions(text) {
  const positions = String(text ?? "")
    .trim()
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [ticker, weight] = line.split(/[\s,]+/);

      // Number("") is 0: a line without a weight must not
      // pass as a zero weight.
      return {
        ticker: ticker.toUpperCase(),
        weight: weight == null || weight === "" ? NaN : Number(weight),
      };
    });

  const total = positions.reduce((sum, position) => sum + position.weight, 0);

  const invalid =
    positions.length === 0 ||
    positions.some(
      (position) =>
        !TICKER.test(position.ticker) ||
        !Number.isFinite(position.weight) ||
        position.weight < 0
    ) ||
    new Set(positions.map((position) => position.ticker)).size !==
      positions.length ||
    Math.abs(total - 1) > 0.001;

  if (invalid) throw new Error(WEIGHTS_MESSAGE);

  return positions;
}

/**
 * What the editor can say about a draft while it is typed:
 * how many lines, what they add up to, and whether it would
 * be accepted. Never throws.
 */
export function summarizeWeights(text) {
  const weights = String(text ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => Number(line.split(/[\s,]+/)[1] ?? NaN));

  const total = weights.reduce((sum, weight) => sum + weight, 0);

  let valid = true;

  try {
    validatePositions(text);
  } catch {
    valid = false;
  }

  return {
    count: weights.length,
    total: Number.isFinite(total) ? total : null,
    valid,
  };
}

/** Positions of either shape (weight or weight_pct) as editor text. */
export function weightsText(positions) {
  return (positions ?? [])
    .map((position) => `${position.ticker} ${weightOf(position).toFixed(4)}`)
    .join("\n");
}

function weightOf(position) {
  if (typeof position.weight === "number") return position.weight;

  return (position.weight_pct ?? 0) / 100;
}

/**
 * Identity of the book for the analysis cache: the same
 * tickers at the same weights are the same calculation.
 */
export function bookKey(portfolio) {
  if (!portfolio) return null;

  return portfolio.positions
    .map((position) => `${position.ticker}:${weightOf(position).toFixed(4)}`)
    .join(",");
}

export function involves(anomaly, ticker) {
  if (!anomaly) return false;

  return (
    anomaly.ticker === ticker || (anomaly.related_tickers ?? []).includes(ticker)
  );
}

export const RESEARCH_LABEL = {
  open_questions: "Open questions",
  followup: "Follow-up added",
  explained: "Explained",
  running: "Running",
  none: "No investigation",
};

const GAP_KINDS = ["missing_evidence", "evidence_requirement"];

/** Questions a graph asked and nobody has answered yet. */
export function openQuestions(graph) {
  return (graph?.nodes ?? []).filter(
    (node) =>
      GAP_KINDS.includes(node.kind) && node.data?.resolution_status !== "answered"
  );
}

/**
 * What the desk knows about one holding, from the runs whose
 * anomaly involves it (as the ticker or as the other leg).
 *
 * The latest completed run speaks for the holding: an older
 * graph with gaps does not make a newer, answered one "open".
 * `run` is what "Open graph" should open: the newest run that
 * has a graph, else the newest run at all.
 */
export function researchStatus(investigations, ticker) {
  const runs = (investigations ?? [])
    .filter((run) => involves(run.anomaly, ticker))
    .sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));

  const run = runs.find((candidate) => candidate.graph?.nodes) ?? runs[0] ?? null;
  const completed = runs.find((candidate) => candidate.status === "completed");

  const result = (status, open = 0) => ({
    status,
    label: RESEARCH_LABEL[status],
    open,
    runs: runs.length,
    run,
  });

  if (completed) {
    const open = openQuestions(completed.graph).length;

    if (open > 0) return result("open_questions", open);
    if (completed.followups?.length) return result("followup");

    return result("explained");
  }

  if (runs.some((candidate) => ["running", "queued"].includes(candidate.status))) {
    return result("running");
  }

  // Only failed runs: nothing was learnt about the holding.
  return result("none");
}

/**
 * Top positive and negative contributors, largest first.
 *
 * `share` is each bar's length against the single largest
 * move on either side, so the two columns share one scale
 * and a small detractor does not look like a large one.
 */
export function rankContributors(contributions, limit = 3) {
  if (!contributions || contributions.status === "unavailable") {
    return {
      status: "unavailable",
      reason: contributions?.reason ?? "Not calculated",
      positive: [],
      negative: [],
    };
  }

  const entries = Object.entries(contributions).filter(([, value]) =>
    Number.isFinite(value)
  );

  const scale = Math.max(...entries.map(([, value]) => Math.abs(value)), 0);

  const row = ([ticker, value]) => ({
    ticker,
    value,
    share: scale > 0 ? Math.abs(value) / scale : 0,
  });

  return {
    status: "available",
    positive: entries
      .filter(([, value]) => value > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(row),
    negative: entries
      .filter(([, value]) => value < 0)
      .sort((a, b) => a[1] - b[1])
      .slice(0, limit)
      .map(row),
  };
}

/** The most recent anomaly on a holding; ties go to the larger |z|. */
export function latestAnomaly(anomalies, ticker) {
  const matches = (anomalies ?? []).filter((anomaly) => involves(anomaly, ticker));

  if (!matches.length) return null;

  return matches.reduce((latest, anomaly) => {
    const order = String(anomaly.observed_on).localeCompare(String(latest.observed_on));

    if (order !== 0) return order > 0 ? anomaly : latest;

    return severity(anomaly) > severity(latest) ? anomaly : latest;
  });
}

function severity(anomaly) {
  return Math.abs(anomaly.z_score ?? 0);
}

/**
 * The book's pair anomalies as overlay candidates, most
 * severe first, one per pair: the first is the prefill, the
 * rest are the quick picks.
 */
export function pairCandidates(anomalies) {
  const seen = new Set();

  return (anomalies ?? [])
    .filter((anomaly) => anomaly.strategy === "pairs" && anomaly.related_tickers?.[0])
    .sort((a, b) => severity(b) - severity(a))
    .map((anomaly) => ({
      a: anomaly.ticker,
      b: anomaly.related_tickers[0],
      z_score: anomaly.z_score ?? null,
      anomaly,
    }))
    .filter((pair) => {
      const key = `${pair.a}/${pair.b}`;

      if (seen.has(key)) return false;

      seen.add(key);

      return true;
    });
}

/** A metric's value, or null with the reason it is missing. */
export function metricValue(metric) {
  if (metric?.status === "available" && Number.isFinite(metric.value)) {
    return { value: metric.value, reason: null };
  }

  return { value: null, reason: metric?.reason ?? "Not calculated" };
}

/** The holding carrying the largest weight, for the tile's caption. */
export function largestHolding(weights) {
  const entries = Object.entries(weights ?? {});

  if (!entries.length) return null;

  return entries.reduce((largest, entry) => (entry[1] > largest[1] ? entry : largest))[0];
}
