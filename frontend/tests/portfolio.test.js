import assert from "node:assert/strict";
import { test } from "node:test";

import {
  SAMPLE_PORTFOLIO,
  bookKey,
  largestHolding,
  latestAnomaly,
  metricValue,
  openQuestions,
  pairCandidates,
  rankContributors,
  researchStatus,
  summarizeWeights,
  validatePositions,
  weightsText,
} from "../src/lib/portfolio.js";

const MESSAGE = "Use unique tickers and nonnegative decimal weights summing to 1.";

test("validatePositions parses tickers and decimal weights", () => {
  assert.deepEqual(validatePositions("cohu 0.5\nPDFS, 0.5\n"), [
    { ticker: "COHU", weight: 0.5 },
    { ticker: "PDFS", weight: 0.5 },
  ]);

  // Blank lines and the 0.001 tolerance are accepted.
  assert.equal(validatePositions("A 0.3334\n\nB 0.3333\nC 0.3333").length, 3);
  assert.equal(validatePositions("BRK.B 1").at(0).ticker, "BRK.B");
});

test("validatePositions rejects what the server would reject", () => {
  const rejected = [
    "",
    "   ",
    "AAPL 0.5\nAAPL 0.5", // duplicate
    "AAPL 0.5\naapl 0.5", // duplicate once upper-cased
    "AAPL 1.2\nMSFT -0.2", // negative
    "AAPL 0.5\nMSFT 0.4", // sums to 0.9
    "AAPL 0.5\nMSFT 0.502", // outside the tolerance
    "AAPL half\nMSFT 0.5", // not a number
    "AAPL\nMSFT 1", // no weight
    "AAPL,\nMSFT 1", // empty weight is not zero
    "AA PL 1", // "PL" is not a weight
    "A$PL 1", // not a ticker
  ];

  for (const text of rejected) {
    assert.throws(() => validatePositions(text), { message: MESSAGE }, text);
  }
});

test("the sample book is valid and round-trips through the editor text", () => {
  const text = weightsText(SAMPLE_PORTFOLIO.positions);

  assert.equal(text, "COHU 0.5000\nPDFS 0.5000");
  assert.deepEqual(validatePositions(text), SAMPLE_PORTFOLIO.positions);
});

test("summarizeWeights describes a draft without throwing", () => {
  assert.deepEqual(summarizeWeights("COHU 0.5\nPDFS 0.5"), { count: 2, total: 1, valid: true });
  assert.deepEqual(summarizeWeights("COHU 0.5\nPDFS 0.25"), { count: 2, total: 0.75, valid: false });
  assert.deepEqual(summarizeWeights("COHU\nPDFS 0.25"), { count: 2, total: null, valid: false });
  assert.deepEqual(summarizeWeights(""), { count: 0, total: 0, valid: false });
});

test("weightsText and bookKey read weight_pct from the portfolio view", () => {
  const portfolio = {
    positions: [
      { ticker: "NVDA", weight_pct: 61.23456 },
      { ticker: "AMD", weight_pct: 38.76544 },
    ],
  };

  assert.equal(weightsText(portfolio.positions), "NVDA 0.6123\nAMD 0.3877");
  assert.equal(bookKey(portfolio), "NVDA:0.6123,AMD:0.3877");
  assert.equal(bookKey(null), null);
  assert.equal(weightsText(null), "");

  // A reweighted book is a different calculation.
  assert.notEqual(
    bookKey(portfolio),
    bookKey({ positions: [{ ticker: "NVDA", weight_pct: 50 }, { ticker: "AMD", weight_pct: 50 }] })
  );
});

function run(id, anomaly, status, { created_at, nodes = null, followups = [] } = {}) {
  return {
    investigation_id: id,
    anomaly,
    status,
    created_at: created_at ?? `2026-03-0${id}T10:00:00Z`,
    followups,
    graph: nodes ? { nodes, edges: [] } : null,
  };
}

const gap = (status) => ({
  node_id: `gap-${status}`,
  kind: "missing_evidence",
  label: "What changed?",
  data: { resolution_status: status },
});

const claim = { node_id: "claim-1", kind: "claim", label: "Guidance cut", data: {} };

test("researchStatus: no run on the holding", () => {
  const other = run(1, { ticker: "MSFT", related_tickers: [] }, "completed", { nodes: [claim] });

  for (const investigations of [null, [], [other]]) {
    const status = researchStatus(investigations, "AAPL");

    assert.equal(status.status, "none");
    assert.equal(status.label, "No investigation");
    assert.equal(status.run, null);
  }
});

test("researchStatus: open questions beat follow-ups, related tickers count", () => {
  const investigations = [
    run(1, { ticker: "KO", related_tickers: ["PEP"] }, "completed", {
      nodes: [claim, gap("open"), gap("answered"), { ...gap("partial"), kind: "evidence_requirement" }],
      followups: [{ run_id: "f1" }],
    }),
  ];

  const status = researchStatus(investigations, "PEP");

  assert.equal(status.status, "open_questions");
  assert.equal(status.label, "Open questions");
  assert.equal(status.open, 2);
  assert.equal(status.run.investigation_id, 1);
});

test("researchStatus: follow-up added, then explained", () => {
  const anomaly = { ticker: "KO", related_tickers: [] };

  const followed = run(1, anomaly, "completed", {
    nodes: [claim, gap("answered")],
    followups: [{ run_id: "f1" }],
  });

  assert.equal(researchStatus([followed], "KO").label, "Follow-up added");

  const explained = run(2, anomaly, "completed", { nodes: [claim] });

  assert.equal(researchStatus([explained], "KO").label, "Explained");
});

test("researchStatus: the latest completed run speaks for the holding", () => {
  const anomaly = { ticker: "KO", related_tickers: [] };

  const investigations = [
    run(1, anomaly, "completed", { nodes: [gap("open")] }),
    run(2, anomaly, "completed", { nodes: [claim] }),
    run(3, anomaly, "running"),
  ];

  const status = researchStatus(investigations, "KO");

  assert.equal(status.status, "explained");
  assert.equal(status.runs, 3);

  // "Open graph" opens the newest run that has a graph.
  assert.equal(status.run.investigation_id, 2);
});

test("researchStatus: running, and failed runs are not research", () => {
  const anomaly = { ticker: "KO", related_tickers: [] };

  const running = researchStatus([run(1, anomaly, "failed"), run(2, anomaly, "queued")], "KO");

  assert.equal(running.label, "Running");
  assert.equal(running.run.investigation_id, 2);

  assert.equal(researchStatus([run(1, anomaly, "failed")], "KO").label, "No investigation");
});

test("openQuestions tolerates a missing graph", () => {
  assert.deepEqual(openQuestions(null), []);
  assert.deepEqual(openQuestions({}), []);
});

test("rankContributors ranks each side and shares one scale", () => {
  const ranked = rankContributors(
    { A: 0.04, B: -0.02, C: 0.01, D: -0.005, E: 0, F: 0.002, G: 0.03 },
    3
  );

  assert.equal(ranked.status, "available");
  assert.deepEqual(ranked.positive.map((row) => row.ticker), ["A", "G", "C"]);
  assert.deepEqual(ranked.negative.map((row) => row.ticker), ["B", "D"]);

  assert.equal(ranked.positive[0].share, 1);
  assert.equal(ranked.negative[0].share, 0.5);
});

test("rankContributors never invents numbers", () => {
  const unavailable = rankContributors({
    status: "unavailable",
    reason: "Insufficient history: 20 common sessions",
  });

  assert.equal(unavailable.status, "unavailable");
  assert.equal(unavailable.reason, "Insufficient history: 20 common sessions");
  assert.deepEqual(unavailable.positive, []);

  assert.equal(rankContributors(null).status, "unavailable");

  const flat = rankContributors({ A: 0, B: 0 });

  assert.deepEqual(flat.positive, []);
  assert.deepEqual(flat.negative, []);
});

test("latestAnomaly picks the most recent, then the most severe", () => {
  const anomalies = [
    { anomaly_id: "a", ticker: "KO", related_tickers: [], observed_on: "2026-03-02", z_score: 5 },
    { anomaly_id: "b", ticker: "PEP", related_tickers: ["KO"], observed_on: "2026-03-10", z_score: -2.1 },
    { anomaly_id: "c", ticker: "KO", related_tickers: [], observed_on: "2026-03-10", z_score: -3.4 },
    { anomaly_id: "d", ticker: "MSFT", related_tickers: [], observed_on: "2026-03-12", z_score: 9 },
  ];

  assert.equal(latestAnomaly(anomalies, "KO").anomaly_id, "c");
  assert.equal(latestAnomaly(anomalies, "PEP").anomaly_id, "b");
  assert.equal(latestAnomaly(anomalies, "AAPL"), null);
  assert.equal(latestAnomaly(null, "KO"), null);
});

test("pairCandidates: pairs only, most severe first, one per pair", () => {
  const anomalies = [
    { anomaly_id: "1", strategy: "vwap", ticker: "KO", related_tickers: [], z_score: 9 },
    { anomaly_id: "2", strategy: "pairs", ticker: "KO", related_tickers: ["PEP"], z_score: 2.4 },
    { anomaly_id: "3", strategy: "pairs", ticker: "V", related_tickers: ["MA"], z_score: -3.9 },
    { anomaly_id: "4", strategy: "pairs", ticker: "KO", related_tickers: ["PEP"], z_score: 3.1 },
    { anomaly_id: "5", strategy: "pairs", ticker: "XOM", related_tickers: [], z_score: 8 },
  ];

  const pairs = pairCandidates(anomalies);

  assert.deepEqual(
    pairs.map((pair) => [pair.a, pair.b, pair.anomaly.anomaly_id]),
    [
      ["V", "MA", "3"],
      ["KO", "PEP", "4"],
    ]
  );

  assert.deepEqual(pairCandidates(null), []);
});

test("metricValue keeps the reason and never reads unavailable as zero", () => {
  assert.deepEqual(metricValue({ status: "available", value: 0.0123 }), {
    value: 0.0123,
    reason: null,
  });

  assert.deepEqual(metricValue({ status: "unavailable", reason: "Insufficient history", value: null }), {
    value: null,
    reason: "Insufficient history",
  });

  assert.deepEqual(metricValue(undefined), { value: null, reason: "Not calculated" });
});

test("largestHolding names the heaviest position", () => {
  assert.equal(largestHolding({ A: 0.2, B: 0.5, C: 0.3 }), "B");
  assert.equal(largestHolding({}), null);
  assert.equal(largestHolding(undefined), null);
});
