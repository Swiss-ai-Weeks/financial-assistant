export const mockClaimGraph = {
  schema_version: "0.1",

  anomaly_id: "A1",
  candidate_event_id: "EVENT-regulatory-approval",

  primary_claim_id: "claim:EVENT-regulatory-approval",

  causal_score: 88.2,
  causal_classification: "strong_candidate",

  nodes: [
    {
      node_id: "claim:EVENT-regulatory-approval",
      kind: "primary_claim",
      label:
        "Regulatory approval likely contributed materially to the abnormal price move.",
      assessment: "strong",
      score: 0.882,
      rationale:
        "This was the highest-ranked causal candidate for the detected anomaly.",
      evidence_ids: [],
    },

    {
      node_id: "subclaim:materiality",
      kind: "subclaim",
      label:
        "The regulatory event was economically material enough to affect the company.",
      assessment: "strong",
      score: 0.85,
      rationale:
        "The approval concerns the company's principal commercial product.",
      criterion_name: "materiality",
      evidence_ids: ["E1", "E2"],
      method: "model_judgment",
    },

    {
      node_id: "subclaim:temporal_fit",
      kind: "subclaim",
      label:
        "The timing of the event is consistent with the observed market reaction.",
      assessment: "strong",
      score: 1.0,
      rationale:
        "Primary evidence appeared approximately six minutes before the abnormal move.",
      criterion_name: "temporal_fit",
      evidence_ids: ["E1"],
      method: "rule",
    },

    {
      node_id: "subclaim:direction",
      kind: "subclaim",
      label:
        "The direction of the market move is consistent with the event.",
      assessment: "supported",
      score: 0.78,
      rationale:
        "The positive price reaction is directionally consistent with the approval.",
      criterion_name: "directional_consistency",
      evidence_ids: ["E1", "E3"],
      method: "market_model",
    },

    {
      node_id: "evidence:E1",
      kind: "evidence",
      label: "Regulator announcement",
      rationale:
        "Official approval announcement published at 10:02 CET.",
      evidence_ids: ["E1"],
      source_name: "Regulator",
      source_uri: "https://example.com/regulator",
    },

    {
      node_id: "evidence:E2",
      kind: "evidence",
      label: "Independent industry reporting",
      rationale:
        "Independent reporting confirms the approval concerns the company's main product.",
      evidence_ids: ["E2"],
      source_name: "Industry News",
      source_uri: "https://example.com/news",
    },

    {
      node_id: "counter:E3",
      kind: "counter_evidence",
      label: "Broader sector rally",
      assessment: "weak",
      score: 0.35,
      rationale:
        "The sector was also positive, but peer movement was substantially smaller.",
      evidence_ids: ["E3"],
    },

    {
      node_id: "source:regulator",
      kind: "source",
      label: "Primary regulatory source",
      source_name: "Regulator",
      source_uri: "https://example.com/regulator",
    },

    {
      node_id: "alternative:sector",
      kind: "alternative_explanation",
      label: "Broader sector rally",
      assessment: "weak",
      score: 0.42,
      rationale:
        "Sector strength explains part of the move but not its magnitude.",
    },
  ],

  edges: [
    {
      edge_id: "1",
      source: "claim:EVENT-regulatory-approval",
      target: "subclaim:materiality",
      kind: "decomposes_to",
    },
    {
      edge_id: "2",
      source: "claim:EVENT-regulatory-approval",
      target: "subclaim:temporal_fit",
      kind: "decomposes_to",
    },
    {
      edge_id: "3",
      source: "claim:EVENT-regulatory-approval",
      target: "subclaim:direction",
      kind: "decomposes_to",
    },
    {
      edge_id: "4",
      source: "subclaim:materiality",
      target: "evidence:E1",
      kind: "supported_by",
    },
    {
      edge_id: "5",
      source: "subclaim:materiality",
      target: "evidence:E2",
      kind: "supported_by",
    },
    {
      edge_id: "6",
      source: "subclaim:temporal_fit",
      target: "evidence:E1",
      kind: "supported_by",
    },
    {
      edge_id: "7",
      source: "evidence:E1",
      target: "source:regulator",
      kind: "sourced_from",
    },
    {
      edge_id: "8",
      source: "claim:EVENT-regulatory-approval",
      target: "counter:E3",
      kind: "contradicted_by",
    },
    {
      edge_id: "9",
      source: "claim:EVENT-regulatory-approval",
      target: "alternative:sector",
      kind: "competes_with",
    },
  ],

  alternatives: [
    {
      candidate_event_id: "EVENT-sector",
      label: "Broader sector rally",
      score: 42.0,
      classification: "weak",
    },
  ],
};