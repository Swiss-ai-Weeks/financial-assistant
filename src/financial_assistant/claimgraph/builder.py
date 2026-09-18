"""Build an inspectable ClaimGraph from causal-scoring output.

Important:

This module does NOT calculate the causal score.

causal_scoring answers:

    "How plausible is this event as an explanation for the anomaly?"

ClaimGraph answers:

    "What does that explanation depend on, and what supports or weakens it?"
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_assistant.causal_scoring.models import (
    CandidateAssessment,
    CausalClassification,
    CausalScoreResult,
    EvidenceItem,
    EvidenceStance,
)

from .models import (
    AlternativeExplanation,
    ClaimAssessment,
    ClaimGraphResult,
    EdgeKind,
    GraphEdge,
    GraphNode,
    NodeKind,
)


# Human-readable epistemic interpretation of the causal-scoring criteria.
#
# These are intentionally claims rather than metric names so the graph
# represents an argument a human can inspect.
CRITERION_SUBCLAIMS: dict[str, str] = {
    "temporal_fit": (
        "The timing of the event and public evidence is consistent "
        "with the anomaly."
    ),
    "relationship_directness": (
        "The event directly concerns the company, asset, or relevant exposure."
    ),
    "economic_plausibility": (
        "There is an economically plausible mechanism linking the event "
        "to the market move."
    ),
    "materiality": (
        "The event is material enough to plausibly affect the asset."
    ),
    "directional_consistency": (
        "The direction of the observed market move is consistent "
        "with the event."
    ),
    "source_independence": (
        "The supporting evidence comes from sufficiently independent "
        "reporting lineages."
    ),
    "primary_source_support": (
        "The explanation is supported by at least one primary source."
    ),
    "novelty": (
        "The information was sufficiently new to plausibly affect "
        "market expectations."
    ),
    "market_footprint_fit": (
        "The observed market footprint is consistent with the proposed event."
    ),
}


def _criterion_assessment(value: float | None) -> ClaimAssessment:
    """Convert a criterion value into a simple UI-facing assessment."""

    if value is None:
        return ClaimAssessment.INSUFFICIENT_EVIDENCE

    if value >= 0.75:
        return ClaimAssessment.STRONG

    if value >= 0.50:
        return ClaimAssessment.SUPPORTED

    return ClaimAssessment.WEAK


def _primary_assessment(
    classification: CausalClassification,
) -> ClaimAssessment:
    """Translate causal-scoring classification into ClaimGraph language."""

    mapping = {
        CausalClassification.STRONG_CANDIDATE: ClaimAssessment.STRONG,
        CausalClassification.PLAUSIBLE: ClaimAssessment.SUPPORTED,
        CausalClassification.WEAK: ClaimAssessment.WEAK,
        CausalClassification.INSUFFICIENT_EVIDENCE: (
            ClaimAssessment.INSUFFICIENT_EVIDENCE
        ),
        CausalClassification.INELIGIBLE: ClaimAssessment.INELIGIBLE,
    }

    return mapping[classification]


def build_claim_graph(
    *,
    assessment: CandidateAssessment,
    score: CausalScoreResult,
    candidate_label: str,
    alternatives: Sequence[AlternativeExplanation] = (),
) -> ClaimGraphResult:
    """Build a first inspectable graph for one leading causal candidate.

    Parameters
    ----------
    assessment:
        Semantic/evidence assessment produced before deterministic scoring.

    score:
        Reproducible output from CausalCandidateScorer.

    candidate_label:
        Human-readable description of the candidate event, for example
        "Regulatory approval of the company's principal product".

        The current causal-scoring model contains candidate_event_id but
        does not yet contain human-readable event text, so it is passed
        explicitly for now.

    alternatives:
        Optional lower-ranked causal candidates retained as competing
        explanations.
    """

    if assessment.anomaly_id != score.anomaly_id:
        raise ValueError("assessment and score refer to different anomalies")

    if assessment.candidate_event_id != score.candidate_event_id:
        raise ValueError(
            "assessment and score refer to different candidate events"
        )

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # Avoid creating the same evidence/source node multiple times when one
    # evidence item supports several criteria.
    created_evidence: set[str] = set()
    created_sources: set[str] = set()

    evidence_by_id: dict[str, EvidenceItem] = {
        item.evidence_id: item for item in score.evidence
    }

    primary_claim_id = f"claim:{score.candidate_event_id}"

    nodes.append(
        GraphNode(
            node_id=primary_claim_id,
            kind=NodeKind.PRIMARY_CLAIM,
            label=(
                f"{candidate_label} likely contributed to anomaly "
                f"{score.anomaly_id}."
            ),
            assessment=_primary_assessment(score.classification),
            score=score.score / 100.0,
            rationale=(
                f"Causal candidate classified as "
                f"{score.classification.value} with score {score.score:.1f}/100."
            ),
        )
    )

    # ------------------------------------------------------------------
    # Convert causal-scoring criteria into explicit subclaims.
    # ------------------------------------------------------------------

    for criterion_name, criterion in score.criteria.items():
        subclaim_id = f"subclaim:{score.candidate_event_id}:{criterion_name}"

        label = CRITERION_SUBCLAIMS.get(
            criterion_name,
            criterion_name.replace("_", " ").capitalize(),
        )

        nodes.append(
            GraphNode(
                node_id=subclaim_id,
                kind=NodeKind.SUBCLAIM,
                label=label,
                assessment=_criterion_assessment(criterion.value),
                score=criterion.value,
                rationale=criterion.rationale,
                criterion_name=criterion_name,
                evidence_ids=criterion.evidence_ids,
                method=criterion.method.value,
            )
        )

        edges.append(
            GraphEdge(
                edge_id=f"edge:{primary_claim_id}:{subclaim_id}",
                source=primary_claim_id,
                target=subclaim_id,
                kind=EdgeKind.DECOMPOSES_TO,
            )
        )

        # Explicitly expose missing evidence rather than silently allowing
        # an incomplete criterion to disappear.
        if criterion.value is None:
            missing_id = (
                f"missing:{score.candidate_event_id}:{criterion_name}"
            )

            nodes.append(
                GraphNode(
                    node_id=missing_id,
                    kind=NodeKind.MISSING_EVIDENCE,
                    label=f"Evidence missing for: {label}",
                    assessment=ClaimAssessment.INSUFFICIENT_EVIDENCE,
                    rationale=criterion.rationale,
                    criterion_name=criterion_name,
                )
            )

            edges.append(
                GraphEdge(
                    edge_id=f"edge:{missing_id}:{subclaim_id}",
                    source=missing_id,
                    target=subclaim_id,
                    kind=EdgeKind.MISSING_SUPPORT_FOR,
                )
            )

        for evidence_id in criterion.evidence_ids:
            evidence = evidence_by_id.get(evidence_id)

            if evidence is None:
                # The scorer should already protect against this, but the
                # builder remains defensive because this is an integration
                # boundary.
                continue

            _attach_evidence(
                evidence=evidence,
                subclaim_id=subclaim_id,
                nodes=nodes,
                edges=edges,
                created_evidence=created_evidence,
                created_sources=created_sources,
            )

    # ------------------------------------------------------------------
    # Explicit counter-evidence.
    # ------------------------------------------------------------------

    contradiction = score.contradiction_strength

    if contradiction.evidence_ids:
        contradiction_id = f"counter:{score.candidate_event_id}"

        nodes.append(
            GraphNode(
                node_id=contradiction_id,
                kind=NodeKind.COUNTER_EVIDENCE,
                label="Evidence weakening the leading explanation",
                assessment=_criterion_assessment(
                    1.0 - (contradiction.value or 0.0)
                ),
                rationale=contradiction.rationale,
                evidence_ids=contradiction.evidence_ids,
                score=contradiction.value,
                method=contradiction.method.value,
            )
        )

        edges.append(
            GraphEdge(
                edge_id=f"edge:{primary_claim_id}:{contradiction_id}",
                source=primary_claim_id,
                target=contradiction_id,
                kind=EdgeKind.CONTRADICTED_BY,
            )
        )

        for evidence_id in contradiction.evidence_ids:
            evidence = evidence_by_id.get(evidence_id)

            if evidence is None:
                continue

            _attach_evidence(
                evidence=evidence,
                subclaim_id=contradiction_id,
                nodes=nodes,
                edges=edges,
                created_evidence=created_evidence,
                created_sources=created_sources,
            )

    # ------------------------------------------------------------------
    # Competing causal explanations.
    # ------------------------------------------------------------------

    for alternative in alternatives:
        alternative_id = (
            f"alternative:{alternative.candidate_event_id}"
        )

        nodes.append(
            GraphNode(
                node_id=alternative_id,
                kind=NodeKind.ALTERNATIVE_EXPLANATION,
                label=alternative.label,
                assessment=_primary_assessment(
                    alternative.classification
                ),
                score=alternative.score / 100.0,
                rationale=(
                    f"Alternative causal candidate scored "
                    f"{alternative.score:.1f}/100 "
                    f"({alternative.classification.value})."
                ),
            )
        )

        edges.append(
            GraphEdge(
                edge_id=f"edge:{primary_claim_id}:{alternative_id}",
                source=primary_claim_id,
                target=alternative_id,
                kind=EdgeKind.COMPETES_WITH,
            )
        )

    return ClaimGraphResult(
        anomaly_id=score.anomaly_id,
        candidate_event_id=score.candidate_event_id,
        primary_claim_id=primary_claim_id,
        causal_score=score.score,
        causal_classification=score.classification,
        nodes=tuple(nodes),
        edges=tuple(edges),
        alternatives=tuple(alternatives),
    )


def _attach_evidence(
    *,
    evidence: EvidenceItem,
    subclaim_id: str,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    created_evidence: set[str],
    created_sources: set[str],
) -> None:
    """Attach one existing evidence item to a graph subclaim."""

    evidence_node_id = f"evidence:{evidence.evidence_id}"

    if evidence.evidence_id not in created_evidence:
        if evidence.stance is EvidenceStance.CONTRADICTS:
            kind = NodeKind.COUNTER_EVIDENCE
        else:
            kind = NodeKind.EVIDENCE

        nodes.append(
            GraphNode(
                node_id=evidence_node_id,
                kind=kind,
                label=(
                    f"{evidence.source_name} "
                    f"({evidence.role.value.replace('_', ' ')})"
                ),
                rationale=(
                    f"Published {evidence.published_at.isoformat()}; "
                    f"stance={evidence.stance.value}; "
                    f"lineage={evidence.lineage_id}."
                ),
                evidence_ids=(evidence.evidence_id,),
                source_name=evidence.source_name,
                source_uri=evidence.source_uri,
            )
        )

        created_evidence.add(evidence.evidence_id)

    if evidence.stance is EvidenceStance.CONTRADICTS:
        relation = EdgeKind.CONTRADICTED_BY
    elif evidence.stance is EvidenceStance.CONTEXT_ONLY:
        relation = EdgeKind.CONTEXT_FROM
    else:
        relation = EdgeKind.SUPPORTED_BY

    edge_id = (
        f"edge:{subclaim_id}:{evidence_node_id}:{relation.value}"
    )

    # A single evidence item may support multiple subclaims, which is valid.
    if not any(edge.edge_id == edge_id for edge in edges):
        edges.append(
            GraphEdge(
                edge_id=edge_id,
                source=subclaim_id,
                target=evidence_node_id,
                kind=relation,
            )
        )

    # Source nodes are deliberately separate from evidence nodes:
    #
    # claim -> evidence -> source
    #
    # This preserves epistemic provenance in the graph.
    source_key = str(evidence.source_uri or evidence.source_name)
    source_node_id = f"source:{evidence.evidence_id}"

    if source_key not in created_sources:
        nodes.append(
            GraphNode(
                node_id=source_node_id,
                kind=NodeKind.SOURCE,
                label=evidence.source_name,
                source_name=evidence.source_name,
                source_uri=evidence.source_uri,
                rationale=(
                    f"Reporting lineage: {evidence.lineage_id}"
                ),
            )
        )

        created_sources.add(source_key)

    source_edge_id = f"edge:{evidence_node_id}:{source_node_id}"

    if not any(edge.edge_id == source_edge_id for edge in edges):
        edges.append(
            GraphEdge(
                edge_id=source_edge_id,
                source=evidence_node_id,
                target=source_node_id,
                kind=EdgeKind.SOURCED_FROM,
            )
        )