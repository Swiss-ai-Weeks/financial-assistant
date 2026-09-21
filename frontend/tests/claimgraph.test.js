import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  applyCopilotAction,
  buildCopilotViewContext,
} from "../src/lib/claimgraph/copilotContext.js";
import {
  buildInvestigationReport,
  reportExport,
} from "../src/lib/claimgraph/investigationReport.js";
import {
  originalCutoff,
  temporalStatuses,
  temporalView,
  timelineSteps,
} from "../src/lib/claimgraph/temporalModel.js";
import { turnOverlay } from "../src/lib/claimgraph/turns.js";
import {
  quarterlyView,
  toReactFlowNodes,
} from "../src/components/investigation/graphAdapter.js";

const load = (name) =>
  JSON.parse(readFileSync(new URL(`../public/examples/${name}`, import.meta.url)));

const temporal = load("investigation_temporal_demo.json");
const review = load("investigation_review_demo.json");

test("time travel hides what was published after the cutoff", () => {
  const cutoff = originalCutoff(temporal);
  const statuses = temporalStatuses(temporal, cutoff);

  const later = temporal.nodes.filter(
    (node) => statuses.get(node.node_id) === "appeared_after_cutoff"
  );

  assert.ok(later.length > 0, "the teaching case has later documents");

  const then = temporalView(temporal, cutoff);
  const hindsight = temporalView(temporal, "latest");

  assert.ok(then.nodes.length < hindsight.nodes.length);

  for (const node of later) {
    assert.ok(!then.nodes.some((item) => item.node_id === node.node_id));
  }

  const steps = timelineSteps(temporal);

  assert.equal(steps[0].label, "At anomaly");
  assert.equal(steps.at(-1).value, "latest");
});

test("the copilot only sees a bounded view, and may only move it", () => {
  const context = buildCopilotViewContext({
    graph: review,
    workspaceId: "w1",
    model: { label: "Apertus" },
    selected: null,
    cutoff: "latest",
  });

  assert.ok(new TextEncoder().encode(JSON.stringify(context)).length <= 22000);
  assert.ok(context.nodes.length <= 20);

  const calls = [];
  const handlers = {
    select: (node) => calls.push(["select", node.node_id]),
    filters: (value) => calls.push(["filters", value]),
    fit: () => calls.push(["fit"]),
  };

  applyCopilotAction({ type: "show_counter" }, review, handlers);
  applyCopilotAction({ type: "fit_graph" }, review, handlers);
  applyCopilotAction(
    { type: "select_node", node_id: review.nodes[0].node_id },
    review,
    handlers
  );

  assert.deepEqual(calls, [
    ["filters", ["counter"]],
    ["fit"],
    ["select", review.nodes[0].node_id],
  ]);

  assert.throws(() =>
    applyCopilotAction({ type: "select_node", node_id: "nope" }, review, handlers)
  );
  assert.throws(() => applyCopilotAction({ type: "delete_node" }, review, handlers));
});

test("a report is a projection of the graph and keeps every id", () => {
  const report = buildInvestigationReport(review, { cutoff: originalCutoff(review) });

  const ids = new Set(review.nodes.map((node) => node.node_id));

  for (const items of Object.values(report.sections)) {
    for (const item of items) {
      if (item.node_id) assert.ok(ids.has(item.node_id), item.node_id);
    }
  }

  for (const format of ["html", "markdown", "json"]) {
    const file = reportExport(report, format);

    assert.ok(file.text.length > 100);
    assert.ok(file.extension);
  }

  assert.throws(() => buildInvestigationReport(review, { cutoff: "latest" }));
});

test("a turn overlay isolates what one follow-up added", () => {
  const graph = {
    nodes: [{ node_id: "a" }, { node_id: "b" }, { node_id: "c" }],
    edges: [{ edge_id: "e1" }, { edge_id: "e2" }],
    followups: [
      {
        run_id: "FU-1",
        delta: { added_node_ids: ["c"], added_edge_ids: ["e2"] },
      },
    ],
  };

  assert.equal(turnOverlay(graph, null), null);
  assert.deepEqual(turnOverlay(graph, "FU-1").added_node_ids, ["c"]);

  const initial = turnOverlay(graph, "initial");

  assert.deepEqual(initial.added_node_ids, ["a", "b"]);
  assert.deepEqual(initial.added_edge_ids, ["e1"]);
});

test("SEC detail is folded away by default and a quarter opens its own lineage", () => {
  const graph = {
    nodes: [
      { node_id: "h", kind: "hypothesis", label: "h", data: {} },
      {
        node_id: "q1",
        kind: "context",
        label: "Q1",
        data: { subtype: "fundamental_snapshot", entity: "AAA", period_end: "2026-03-31" },
      },
      {
        node_id: "obs",
        kind: "observation",
        label: "revenue",
        data: { metadata: { provider: "SEC EDGAR" } },
      },
      {
        node_id: "growth",
        kind: "calculation",
        label: "revenue growth",
        data: {
          metadata: {
            metric_id: "revenue_yoy_growth",
            frequency: "quarterly",
            period_end: "2026-03-31",
            ticker: "AAA",
          },
        },
      },
    ],
    edges: [{ edge_id: "e", source: "q1", target: "obs", kind: "derived_from" }],
  };

  const folded = quarterlyView(graph).nodes.map((node) => node.node_id);

  assert.deepEqual(folded, ["h", "q1", "growth"]);

  const opened = quarterlyView(graph, { expanded: ["q1"] }).nodes.map((n) => n.node_id);

  assert.ok(opened.includes("obs"));
  assert.equal(quarterlyView(graph, { showAtomic: true }).nodes.length, 4);
});

test("every node kind of a follow-up has a lane", () => {
  const kinds = ["anomaly", "hypothesis", "context", "agent_action", "tool_call", "model_run"];

  const placed = toReactFlowNodes(
    kinds.map((kind, index) => ({ node_id: `n${index}`, kind, label: kind }))
  );

  assert.equal(placed.length, kinds.length);

  for (const node of placed) {
    assert.ok(Number.isFinite(node.position.x) && Number.isFinite(node.position.y));
    assert.ok(node.data.displayKind);
  }
});
