/*
 * ClaimGraph v0.2 -> ReactFlow.
 *
 * Nodes are laid out in horizontal lanes, one per kind,
 * reading top-down from the anomaly to its sources. A
 * lane wraps onto as many rows as it needs and pushes
 * the following lanes down, so lanes never overlap.
 */

const LANES = [
  ["anomaly"],
  ["hypothesis"],
  ["claim"],
  ["assumption"],
  ["evidence_requirement", "missing_evidence"],
  ["inference"],
  ["context"],
  ["calculation"],
  ["observation"],
  ["document"],
  ["source"],
];

const KIND_LABELS = {
  anomaly: "Anomaly",
  source: "Source",
  document: "Document",
  claim: "Claim",
  hypothesis: "Hypothesis",
  assumption: "Assumption",
  evidence_requirement: "Evidence requirement",
  missing_evidence: "Missing evidence",
  observation: "Observation",
  calculation: "Calculation",
  inference: "Inference",
  model_run: "Model run",
  context: "Context",
  agent_action: "Follow-up",
  research_task: "Research task",
  tool_call: "Tool call",
};

export const kindLabel = (kind) =>
  KIND_LABELS[kind] ?? String(kind ?? "").replaceAll("_", " ");

const COLUMNS = 4;
const COLUMN_WIDTH = 300;
const ROW_HEIGHT = 176;
const LANE_GAP = 70;

// Execution provenance gets its own lane on the right.
const MODEL_RUN_X = COLUMNS * COLUMN_WIDTH + 140;
const MODEL_RUN_COLUMNS = 2;

function lanePositions(graphNodes) {
  const positions = new Map();
  let top = 0;

  for (const kinds of LANES) {
    const members = graphNodes.filter((node) => kinds.includes(node.kind));

    if (members.length === 0) continue;

    // A short lane is centred under the anomaly.
    const width = Math.min(members.length, COLUMNS) * COLUMN_WIDTH;
    const left = (COLUMNS * COLUMN_WIDTH - width) / 2;

    members.forEach((node, index) => {
      positions.set(node.node_id, {
        x: left + (index % COLUMNS) * COLUMN_WIDTH,
        y: top + Math.floor(index / COLUMNS) * ROW_HEIGHT,
      });
    });

    top += Math.ceil(members.length / COLUMNS) * ROW_HEIGHT + LANE_GAP;
  }

  graphNodes
    .filter((node) => !positions.has(node.node_id))
    .forEach((node, index) => {
      positions.set(node.node_id, {
        x: MODEL_RUN_X + (index % MODEL_RUN_COLUMNS) * COLUMN_WIDTH,
        y: Math.floor(index / MODEL_RUN_COLUMNS) * ROW_HEIGHT,
      });
    });

  return positions;
}

export function toReactFlowNodes(graphNodes) {
  const positions = lanePositions(graphNodes);

  return graphNodes.map((node) => ({
    id: node.node_id,
    position: positions.get(node.node_id),
    data: {
      ...node,
      inspectorType: "node",
      displayKind: KIND_LABELS[node.kind] ?? node.kind,
      label: node.label,
    },
    className: `cg-node cg-node--${node.kind}`,
  }));
}

export function toReactFlowEdges(graphEdges) {
  return graphEdges.map((edge) => {
    const challenges = ["contradicts", "weakens", "competes_with"].includes(
      edge.kind
    );

    const label = edge.kind.replaceAll("_", " ");

    return {
      id: edge.edge_id,
      source: edge.source,
      target: edge.target,
      label,
      animated: challenges,
      className: `cg-edge cg-edge--${edge.kind}`,
      data: {
        inspectorType: "edge",
        edge_id: edge.edge_id,
        source: edge.source,
        target: edge.target,
        kind: edge.kind,
        displayKind: "Relationship",
        label,
        ...edge.data,
      },
    };
  });
}


/*
 * SEC filings put hundreds of figures into a graph: every
 * XBRL fact, its filing, and every metric computed from them.
 * Shown all at once they bury the argument. By default only
 * the latest quarter's headline trends stay on the canvas;
 * a clicked quarter reveals its own lineage, and two toggles
 * bring back the atomic evidence and the older quarters.
 *
 * This changes presentation only: the inspector, the report
 * and the review keep working on the full graph.
 */
const LINEAGE = ["derived_from", "calculated_from", "extracted_from", "published_by"];

const HEADLINE_METRIC =
  /^(revenue|operating_margin|operating_cash_flow|free_cash_flow_margin|cash|net_debt|shares_outstanding)_(qoq|yoy)_(growth|change)$/;

export function quarterlyView(
  graph,
  { showAtomic = false, showOlder = false, expanded = [] } = {}
) {
  const hasSnapshots = graph.nodes.some(
    (node) => node.data?.subtype === "fundamental_snapshot"
  );

  if (!hasSnapshots) return graph;

  const revealed = new Set();

  const reveal = (id) => {
    if (revealed.has(id)) return;

    revealed.add(id);

    graph.edges
      .filter((edge) => edge.source === id && LINEAGE.includes(edge.kind))
      .forEach((edge) => reveal(edge.target));
  };

  expanded.forEach(reveal);

  const latest = new Map();

  graph.nodes.forEach((node) => {
    const data = node.data;

    if (data?.subtype !== "fundamental_snapshot") return;

    if (!latest.has(data.entity) || latest.get(data.entity) < data.period_end) {
      latest.set(data.entity, data.period_end);
    }
  });

  const nodes = graph.nodes.filter((node) => {
    if (showAtomic || revealed.has(node.node_id)) return true;

    const data = node.data ?? {};
    const meta = data.metadata ?? {};
    const fromSec = meta.provider === "SEC EDGAR";

    if (data.older_quarter && !showOlder) return false;
    if (["observation", "document"].includes(node.kind) && fromSec) return false;
    if (node.kind === "source" && /SEC EDGAR/.test(node.label)) return false;

    if (node.kind === "calculation" && meta.metric_id) {
      return (
        meta.frequency === "quarterly" &&
        meta.period_end === latest.get(meta.ticker) &&
        HEADLINE_METRIC.test(meta.metric_id) &&
        (meta.metric_id.includes("margin") || meta.metric_id.endsWith("growth"))
      );
    }

    return true;
  });

  const ids = new Set(nodes.map((node) => node.node_id));

  return {
    ...graph,
    nodes,
    edges: graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)),
  };
}
