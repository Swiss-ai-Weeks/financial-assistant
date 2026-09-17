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
const WRAP_Y_GAP = 140;


export function toReactFlowNodes(
  graphNodes
) {
  const counters = {};

  return graphNodes.map((node) => {
    counters[node.kind] =
      counters[node.kind] ?? 0;

    const index =
      counters[node.kind]++;

    let x;
    let y;

    if (node.kind === "anomaly") {
      x = 500;
      y = ROWS.anomaly;
    } else if (
      node.kind === "model_run"
    ) {
      // Execution provenance gets its
      // own lane on the right.
      x =
        1400
        + (index % 2) * 310;

      y =
        220
        + Math.floor(index / 2)
          * 150;
    } else {
      x =
        60
        + (index % MAIN_COLUMNS)
          * MAIN_X_GAP;

      y =
        (ROWS[node.kind] ?? 700)
        + Math.floor(
          index / MAIN_COLUMNS
        ) * WRAP_Y_GAP;
    }

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

      animated:
        isChallengeRelation,

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
