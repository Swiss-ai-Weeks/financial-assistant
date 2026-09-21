import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MATCH_THRESHOLD,
  agreement,
  arrange,
  candidates,
  comparisons,
  readers,
  similarity,
  summarize,
} from "../src/lib/claimgraph/compare.js";

const EARNINGS = "Quarterly earnings beat analyst expectations on strong data center revenue";
const EARNINGS_REWORDED =
  "Strong data center revenue pushed quarterly earnings above analyst expectations";
const EXPORTS = "New export restrictions on chips to China hurt the outlook";
const LAWSUIT = "A shareholder lawsuit over accounting disclosures spooked investors";

function hypothesis(text, score = 1, extra = {}) {
  return {
    hypothesis_id: text.slice(0, 12),
    text,
    score,
    supporting: 2,
    contradicting: 1,
    weakening: 1,
    context: 0,
    assumptions: [],
    missing_information: [],
    ...extra,
  };
}

function anomaly(id, ticker = "NVDA") {
  return {
    anomaly_id: id,
    ticker,
    related_tickers: [],
    strategy: "vwap",
    kind: "volume_spike",
    observed_on: "2026-03-02",
    z_score: 4.2,
    summary: `${ticker} moved`,
  };
}

let sequence = 0;

function run({
  anomalyId = "a1",
  ticker,
  modelId = "nemotron",
  status = "completed",
  created = "2026-03-02T10:00:00Z",
  finished = "2026-03-02T10:01:30Z",
  hypotheses = [hypothesis(EARNINGS, 2)],
  ...extra
} = {}) {
  sequence += 1;

  return {
    investigation_id: `run-${sequence}`,
    anomaly: anomaly(anomalyId, ticker),
    status,
    created_at: created,
    finished_at: status === "completed" || status === "failed" ? finished : null,
    error: status === "failed" ? "model unreachable" : null,
    model: `vendor/${modelId}`,
    model_id: modelId,
    model_label: modelId,
    model_local: modelId === "apertus",
    usage: { calls: 5, latency_ms: 1000, prompt_tokens: 1200, completion_tokens: 300 },
    stages: [],
    hypotheses: status === "completed" ? hypotheses : [],
    claims: [{}, {}, {}],
    documents_used: 7,
    fundamentals: [],
    followups: [{}],
    graph: {
      nodes: [
        { kind: "calculation" },
        { kind: "missing_evidence" },
        { kind: "evidence_requirement" },
        { kind: "claim" },
      ],
    },
    ...extra,
  };
}

test("similarity ignores word order and stopwords", () => {
  assert.ok(similarity(EARNINGS, EARNINGS_REWORDED) >= MATCH_THRESHOLD);
  assert.ok(similarity(EARNINGS, LAWSUIT) < MATCH_THRESHOLD);
  assert.equal(similarity("", EARNINGS), 0);
  assert.equal(similarity(null, undefined), 0);
});

test("summarize turns a run into one column", () => {
  const column = summarize(run({ modelId: "apertus" }));

  assert.equal(column.model_id, "apertus");
  assert.equal(column.local, true);
  assert.equal(column.seconds, 90);
  assert.equal(column.calls, 5);
  assert.equal(column.prompt_tokens, 1200);
  assert.equal(column.completion_tokens, 300);
  assert.equal(column.documents, 7);
  assert.equal(column.claims, 3);
  assert.equal(column.supporting, 2);
  assert.equal(column.countering, 2);
  assert.equal(column.sec, 1);
  assert.equal(column.gaps, 2);
  assert.equal(column.followups, 1);
  assert.equal(column.has_graph, true);
  assert.equal(column.best.text, EARNINGS);
});

test("summarize copes with a run that is still reading", () => {
  const column = summarize(
    run({ status: "running", graph: null, usage: undefined, model_id: undefined })
  );

  assert.equal(column.model_id, "default");
  assert.equal(column.seconds, null);
  assert.equal(column.calls, 0);
  assert.equal(column.best, null);
  assert.equal(column.has_graph, false);
  assert.equal(column.gaps, 0);
});

test("comparisons groups runs by anomaly, newest first", () => {
  const groups = comparisons([
    run({ anomalyId: "old", ticker: "AMD", created: "2026-03-01T09:00:00Z" }),
    run({ anomalyId: "new", ticker: "NVDA", created: "2026-03-03T09:00:00Z" }),
    run({
      anomalyId: "old",
      ticker: "AMD",
      modelId: "apertus",
      created: "2026-03-01T09:30:00Z",
    }),
  ]);

  assert.deepEqual(
    groups.map((group) => group.anomaly.anomaly_id),
    ["new", "old"]
  );
  assert.deepEqual(
    groups[1].columns.map((column) => column.model_id),
    ["apertus", "nemotron"]
  );
  assert.equal(groups[0].columns.length, 1);
});

test("comparisons tolerates no investigations", () => {
  assert.deepEqual(comparisons(null), []);
  assert.deepEqual(comparisons([]), []);
});

test("the latest run of a model replaces its earlier ones", () => {
  const earlier = run({ created: "2026-03-02T10:00:00Z" });
  const later = run({
    created: "2026-03-02T12:00:00Z",
    hypotheses: [hypothesis(EXPORTS, 1)],
  });

  const [group] = comparisons([earlier, later]);

  assert.equal(group.columns.length, 1);
  assert.equal(group.columns[0].investigation_id, later.investigation_id);
  assert.equal(group.columns[0].best.text, EXPORTS);
});

test("a completed run wins over a newer failed or unfinished one", () => {
  const completed = run({ created: "2026-03-02T10:00:00Z" });
  const failed = run({ status: "failed", created: "2026-03-02T12:00:00Z" });

  const [group] = comparisons([failed, completed]);

  assert.equal(group.columns.length, 1);
  assert.equal(group.columns[0].investigation_id, completed.investigation_id);
  assert.equal(group.columns[0].status, "completed");

  const [onlyFailed] = comparisons([failed]);

  assert.equal(onlyFailed.columns[0].status, "failed");
  assert.equal(onlyFailed.columns[0].error, "model unreachable");
});

test("agreement is null with a single run", () => {
  const [group] = comparisons([run()]);

  assert.equal(group.agreement, null);
  assert.equal(readers(group.agreement), 0);
});

test("agreement is null until a second model has completed", () => {
  const [group] = comparisons([
    run(),
    run({ modelId: "apertus", status: "running", created: "2026-03-02T11:00:00Z" }),
  ]);

  assert.equal(group.columns.length, 2);
  assert.equal(group.agreement, null);
});

test("same_best is true when both models lead with the same explanation", () => {
  const [group] = comparisons([
    run({ hypotheses: [hypothesis(EARNINGS, 2), hypothesis(EXPORTS, -1)] }),
    run({
      modelId: "apertus",
      created: "2026-03-02T11:00:00Z",
      hypotheses: [hypothesis(EARNINGS_REWORDED, 1.5), hypothesis(EXPORTS, 0.5)],
    }),
  ]);

  const result = group.agreement;

  assert.equal(result.reference, "apertus");
  assert.equal(result.same_best, true);
  assert.equal(result.shared, 2);
  assert.equal(result.total, 2);
  assert.equal(readers(result), 2);
  assert.equal(result.rows[0].matches[0].model_id, "nemotron");
  assert.equal(result.rows[0].matches[0].text, EARNINGS);
  assert.equal(result.rows[0].matches[0].score, 2);
  assert.ok(result.rows[0].matches[0].overlap >= MATCH_THRESHOLD);
});

test("same_best is false when the models lead with different explanations", () => {
  const result = agreement(
    [
      run({ hypotheses: [hypothesis(EARNINGS, 2), hypothesis(EXPORTS, 1)] }),
      run({
        modelId: "apertus",
        hypotheses: [hypothesis(EXPORTS, 2), hypothesis(EARNINGS_REWORDED, 1)],
      }),
    ].map(summarize)
  );

  assert.equal(result.reference, "nemotron");
  assert.equal(result.same_best, false);
  // Ranked differently, yet both explanations exist on each side.
  assert.equal(result.shared, 2);
});

test("a hypothesis without a counterpart is reported as such", () => {
  const result = agreement(
    [
      run({ hypotheses: [hypothesis(EARNINGS, 2), hypothesis(LAWSUIT, 1)] }),
      run({ modelId: "apertus", hypotheses: [hypothesis(EARNINGS_REWORDED, 2)] }),
    ].map(summarize)
  );

  const [matched, orphan] = result.rows;

  assert.equal(matched.matches[0].text, EARNINGS_REWORDED);
  assert.equal(orphan.text, LAWSUIT);
  assert.equal(orphan.matches[0].model_id, "apertus");
  assert.equal(orphan.matches[0].text, null);
  assert.equal(orphan.matches[0].score, null);
  assert.ok(orphan.matches[0].overlap < MATCH_THRESHOLD);
  assert.equal(result.same_best, true);
  assert.equal(result.shared, 1);
  assert.equal(result.total, 2);
});

test("every other model must share an explanation for it to count", () => {
  const result = agreement(
    [
      run({ hypotheses: [hypothesis(EARNINGS, 2)] }),
      run({ modelId: "apertus", hypotheses: [hypothesis(EARNINGS_REWORDED, 2)] }),
      run({ modelId: "third", hypotheses: [hypothesis(LAWSUIT, 2)] }),
    ].map(summarize)
  );

  assert.equal(readers(result), 3);
  assert.equal(result.rows[0].matches.length, 2);
  assert.equal(result.shared, 0);
  assert.equal(result.same_best, false);
});

test("arrange puts the focused anomaly first, then multi-model anomalies", () => {
  const groups = comparisons([
    run({ anomalyId: "single-new", created: "2026-03-05T09:00:00Z" }),
    run({ anomalyId: "pair", created: "2026-03-04T09:00:00Z" }),
    run({ anomalyId: "pair", modelId: "apertus", created: "2026-03-04T10:00:00Z" }),
    run({ anomalyId: "single-old", created: "2026-03-01T09:00:00Z" }),
  ]);

  const ids = (list) => list.map((group) => group.anomaly.anomaly_id);

  assert.deepEqual(ids(arrange(groups)), ["pair", "single-new", "single-old"]);
  assert.deepEqual(ids(arrange(groups, "single-old")), [
    "single-old",
    "pair",
    "single-new",
  ]);
  assert.deepEqual(ids(arrange(groups, "unknown")), ["pair", "single-new", "single-old"]);
});

test("candidates are analysis models that have not read the anomaly", () => {
  const modelList = {
    default_id: "nemotron",
    egress_policy: "external_allowed",
    models: [
      { id: "nemotron", label: "Nemotron", roles: ["analysis", "interaction"], default: true },
      { id: "apertus", label: "Apertus", roles: ["analysis"] },
      { id: "chat", label: "Chat only", roles: ["interaction"] },
    ],
  };

  const ids = (columns) => candidates(modelList, columns).map((model) => model.id);

  assert.deepEqual(ids([summarize(run())]), ["apertus"]);
  assert.deepEqual(ids([summarize(run({ model_id: undefined }))]), ["apertus"]);
  assert.deepEqual(ids([]), ["nemotron", "apertus"]);
  assert.deepEqual(candidates(null, []), []);
});
