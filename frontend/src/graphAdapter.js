const ROWS = {
  anomaly: 40,

  hypothesis: 220,

  claim: 420,

  evidence_requirement: 590,
  inference: 590,

  calculation: 760,

  observation: 930,

  document: 1100,

  source: 1270,
  model_run: 1270,

  missing_evidence: 760,
};


const KIND_LABELS = {
  anomaly: "Anomaly",
  source: "Source",
  document: "Document",
  claim: "Claim",
  hypothesis: "Hypothesis",
  evidence_requirement: "Evidence requirement",
  observation: "Observation",
  calculation: "Calculation",
  inference: "Inference",
  model_run: "Model run",
  missing_evidence: "Missing evidence",
};


export function toReactFlowNodes(graphNodes) {
  const counters = {};

  return graphNodes.map((node) => {
    counters[node.kind] =
      counters[node.kind] ?? 0;

    const index = counters[node.kind]++;

    let x = 60 + index * 310;

    // Keep the anomaly roughly centred.
    if (node.kind === "anomaly") {
      x = 520;
    }

    // Execution provenance sits off to the side.
    if (node.kind === "model_run") {
      x = 900 + index * 310;
    }

    return {
      id: node.node_id,

      position: {
        x,
        y: ROWS[node.kind] ?? 600,
      },

      data: {
        ...node,

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


export function toReactFlowEdges(graphEdges) {
  return graphEdges.map((edge) => {
    const isChallengeRelation = [
      "contradicts",
      "weakens",
      "competes_with",
    ].includes(edge.kind);

    return {
      id: edge.edge_id,

      source: edge.source,
      target: edge.target,

      label:
        edge.kind.replaceAll("_", " "),

      animated: isChallengeRelation,

      data: {
        ...edge.data,
        kind: edge.kind,
      },
    };
  });
}
