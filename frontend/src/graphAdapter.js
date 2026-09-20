const ROWS = {
  anomaly: 40,

  hypothesis: 220,

  claim: 440,

  assumption: 660,

  evidence_requirement: 900,
  missing_evidence: 900,

  inference: 1120,
  calculation: 1320,
  observation: 1520,

  document: 1740,
  source: 1940,
};


const KIND_LABELS = {
  anomaly: "Anomaly",
  source: "Source",
  document: "Document",

  claim: "Claim",
  hypothesis: "Hypothesis",

  assumption: "Assumption",

  evidence_requirement:
    "Evidence requirement",

  missing_evidence:
    "Missing evidence",

  observation: "Observation",
  calculation: "Calculation",
  inference: "Inference",

  model_run: "Model run",
};


const MAIN_COLUMNS = 4;
const MAIN_X_GAP = 310;
const WRAP_Y_GAP = 190;


export function toReactFlowNodes(
  graphNodes
) {
  const counters = {};
  const bases = {};
  let nextY = 40;
  const kinds = [...new Set(graphNodes.map(node => node.kind))]
    .filter(kind => kind !== "model_run")
    .sort((a, b) => (ROWS[a] ?? 700) - (ROWS[b] ?? 700));
  for (const kind of kinds) {
    bases[kind] = nextY;
    const count = graphNodes.filter(node => node.kind === kind).length;
    nextY += Math.ceil(count / MAIN_COLUMNS) * WRAP_Y_GAP + 70;
  }

  return graphNodes.map((node) => {
    const index = counters[node.kind] ?? 0;
    counters[node.kind] = index + 1;
    const execution = node.kind === "model_run";
    const x = execution ? 1400 + (index % 2) * MAIN_X_GAP
      : 60 + (index % MAIN_COLUMNS) * MAIN_X_GAP;
    const y = execution ? 220 + Math.floor(index / 2) * WRAP_Y_GAP
      : bases[node.kind] + Math.floor(index / MAIN_COLUMNS) * WRAP_Y_GAP;

    return {
      id: node.node_id,

      position: {
        x,
        y,
      },

      data: {
        ...node,

        inspectorType: "node",

        displayKind:
          KIND_LABELS[node.kind]
          ?? node.kind,

        label: node.label,
      },

      className:
        `cg-node cg-node--${node.kind}`,
    };
  });
}


export function toReactFlowEdges(
  graphEdges
) {
  return graphEdges.map((edge) => {
    const isChallengeRelation = [
      "contradicts",
      "weakens",
      "competes_with",
    ].includes(edge.kind);

    const label =
      edge.kind.replaceAll(
        "_",
        " "
      );

    return {
      id: edge.edge_id,

      source: edge.source,
      target: edge.target,

      label,

      animated: false,

      style: isChallengeRelation ? { stroke: "#dd8796", strokeWidth: 2 } : undefined,

      className:
        `cg-edge cg-edge--${edge.kind}`,

      data: {
        inspectorType: "edge",

        edge_id: edge.edge_id,

        source: edge.source,
        target: edge.target,

        kind: edge.kind,

        displayKind:
          "Relationship",

        label,

        ...edge.data,
      },
    };
  });
}
