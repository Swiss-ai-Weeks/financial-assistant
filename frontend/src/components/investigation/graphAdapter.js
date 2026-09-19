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
};

const COLUMNS = 4;
const COLUMN_WIDTH = 300;
const ROW_HEIGHT = 130;
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
