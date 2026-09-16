from datetime import datetime, timedelta, timezone

from financial_assistant.causal_scoring.models import (
    CandidateAssessment,
    CriterionMethod,
    CriterionScore,
    EvidenceItem,
    EvidenceRole,
    EvidenceStance,
)
from financial_assistant.causal_scoring.scorer import CausalCandidateScorer

from financial_assistant.claimgraph import (
    AlternativeExplanation,
    NodeKind,
    build_claim_graph,
)


UTC = timezone.utc


def criterion(
    value: float | None,
    *evidence_ids: str,
) -> CriterionScore:
    return CriterionScore(
        value=value,
        rationale="Test criterion rationale.",
        evidence_ids=evidence_ids,
        method=CriterionMethod.MODEL_JUDGMENT,
    )


def test_build_claim_graph_from_causal_score() -> None:
    anomaly_start = datetime(2026, 9, 14, 10, 8, tzinfo=UTC)
    anomaly_end = anomaly_start + timedelta(hours=1)

    evidence = (
        EvidenceItem(
            evidence_id="E1",
            source_name="Regulator",
            source_uri="https://example.com/regulator",
            published_at=anomaly_start - timedelta(minutes=6),
            lineage_id="regulator-primary",
            role=EvidenceRole.PRIMARY_SOURCE,
            stance=EvidenceStance.SUPPORTS,
        ),
        EvidenceItem(
            evidence_id="E2",
            source_name="Independent News",
            source_uri="https://example.com/news",
            published_at=anomaly_start + timedelta(minutes=10),
            lineage_id="independent-news",
            role=EvidenceRole.INDEPENDENT_REPORTING,
            stance=EvidenceStance.SUPPORTS,
        ),
        EvidenceItem(
            evidence_id="E3",
            source_name="Sector Commentary",
            source_uri="https://example.com/sector",
            published_at=anomaly_start + timedelta(minutes=15),
            lineage_id="sector-commentary",
            role=EvidenceRole.SECONDARY_ANALYSIS,
            stance=EvidenceStance.CONTRADICTS,
        ),
    )

    assessment = CandidateAssessment(
        anomaly_id="A1",
        candidate_event_id="EVENT-regulatory-approval",
        anomaly_start_at=anomaly_start,
        anomaly_end_at=anomaly_end,
        as_of_at=anomaly_end,
        evidence=evidence,
        relationship_directness=criterion(0.95, "E1"),
        economic_plausibility=criterion(0.90, "E1"),
        materiality=criterion(0.85, "E1", "E2"),
        directional_consistency=criterion(0.90, "E2"),
        novelty=criterion(0.80, "E1"),
        market_footprint_fit=criterion(0.85, "E2"),
    )

    score = CausalCandidateScorer().score(assessment)

    graph = build_claim_graph(
        assessment=assessment,
        score=score,
        candidate_label=(
            "Regulatory approval of the company's principal product"
        ),
        alternatives=(
            AlternativeExplanation(
                candidate_event_id="EVENT-sector-rally",
                label="Broader sector rally",
                score=42.0,
                classification="weak",
            ),
        ),
    )

    assert graph.anomaly_id == "A1"
    assert graph.candidate_event_id == "EVENT-regulatory-approval"

    primary_nodes = [
        node
        for node in graph.nodes
        if node.kind is NodeKind.PRIMARY_CLAIM
    ]

    assert len(primary_nodes) == 1

    subclaims = [
        node
        for node in graph.nodes
        if node.kind is NodeKind.SUBCLAIM
    ]

    assert subclaims

    evidence_nodes = [
        node
        for node in graph.nodes
        if node.kind in {
            NodeKind.EVIDENCE,
            NodeKind.COUNTER_EVIDENCE,
        }
    ]

    assert evidence_nodes

    alternative_nodes = [
        node
        for node in graph.nodes
        if node.kind is NodeKind.ALTERNATIVE_EXPLANATION
    ]

    assert len(alternative_nodes) == 1


def test_missing_criterion_becomes_visible_missing_evidence_node() -> None:
    anomaly_start = datetime(2026, 9, 14, 10, 8, tzinfo=UTC)
    anomaly_end = anomaly_start + timedelta(hours=1)

    evidence = (
        EvidenceItem(
            evidence_id="E1",
            source_name="Primary Source",
            source_uri="https://example.com/source",
            published_at=anomaly_start - timedelta(minutes=5),
            lineage_id="primary",
            role=EvidenceRole.PRIMARY_SOURCE,
            stance=EvidenceStance.SUPPORTS,
        ),
    )

    assessment = CandidateAssessment(
        anomaly_id="A2",
        candidate_event_id="EVENT-2",
        anomaly_start_at=anomaly_start,
        anomaly_end_at=anomaly_end,
        as_of_at=anomaly_end,
        evidence=evidence,
        relationship_directness=criterion(0.9, "E1"),
        economic_plausibility=criterion(0.8, "E1"),

        # Deliberately unresolved.
        materiality=criterion(None),

        directional_consistency=criterion(0.8, "E1"),
        novelty=criterion(0.8, "E1"),
        market_footprint_fit=criterion(0.8, "E1"),
    )

    score = CausalCandidateScorer().score(assessment)

    graph = build_claim_graph(
        assessment=assessment,
        score=score,
        candidate_label="Example event",
    )

    missing_nodes = [
        node
        for node in graph.nodes
        if node.kind is NodeKind.MISSING_EVIDENCE
    ]

    assert any(
        node.criterion_name == "materiality"
        for node in missing_nodes
    )