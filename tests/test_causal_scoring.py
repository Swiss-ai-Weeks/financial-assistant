from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from financial_assistant.causal_scoring import (
    CandidateAssessment,
    CausalCandidateScorer,
    CausalClassification,
    CriterionMethod,
    CriterionScore,
    EvidenceItem,
    EvidenceRole,
    EvidenceStance,
    ScorerConfig,
)


ANOMALY_START = datetime(2024, 5, 30, 13, 30, tzinfo=UTC)
ANOMALY_END = datetime(2024, 5, 30, 20, 0, tzinfo=UTC)


def evidence(
    evidence_id: str,
    *,
    published_at: datetime,
    role: EvidenceRole,
    stance: EvidenceStance = EvidenceStance.SUPPORTS,
    lineage_id: str | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_name=evidence_id,
        published_at=published_at,
        lineage_id=lineage_id or evidence_id,
        role=role,
        stance=stance,
    )


def criterion(
    value: float | None,
    *evidence_ids: str,
    method: CriterionMethod = CriterionMethod.MODEL_JUDGMENT,
) -> CriterionScore:
    return CriterionScore(
        value=value,
        rationale="Fixture criterion with traceable support.",
        evidence_ids=evidence_ids,
        method=method,
    )


def hpq_assessment(
    *,
    extra_evidence: tuple[EvidenceItem, ...] = (),
    relationship: CriterionScore | None = None,
) -> CandidateAssessment:
    primary = evidence(
        "hp_release",
        published_at=datetime(2024, 5, 29, 20, 5, tzinfo=UTC),
        role=EvidenceRole.PRIMARY_SOURCE,
    )
    independent = evidence(
        "independent_report",
        published_at=datetime(2024, 5, 30, 12, 0, tzinfo=UTC),
        role=EvidenceRole.INDEPENDENT_REPORTING,
    )
    market = evidence(
        "market_close",
        published_at=ANOMALY_END,
        role=EvidenceRole.MARKET_DATA,
    )
    return CandidateAssessment(
        anomaly_id="TECH-007",
        candidate_event_id="hpq-q2-2024-results",
        anomaly_start_at=ANOMALY_START,
        anomaly_end_at=ANOMALY_END,
        as_of_at=ANOMALY_END,
        evidence=(primary, independent, market, *extra_evidence),
        relationship_directness=relationship or criterion(1.0, "hp_release"),
        economic_plausibility=criterion(0.9, "hp_release"),
        materiality=criterion(0.75, "hp_release", "independent_report"),
        directional_consistency=criterion(
            1.0,
            "market_close",
            method=CriterionMethod.MARKET_MODEL,
        ),
        novelty=criterion(0.8, "hp_release"),
        market_footprint_fit=criterion(
            0.95,
            "market_close",
            method=CriterionMethod.MARKET_MODEL,
        ),
    )


class CausalCandidateScorerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = CausalCandidateScorer()

    def test_strong_direct_candidate_is_fully_traceable(self) -> None:
        result = self.scorer.score(hpq_assessment())

        self.assertTrue(result.eligible)
        self.assertEqual(result.classification, CausalClassification.STRONG_CANDIDATE)
        self.assertEqual(result.score, 91.2)
        self.assertEqual(result.evidence_coverage, 1.0)
        self.assertEqual(result.missing_criteria, ())
        self.assertEqual(result.policy.version, "causal-candidate-v1")
        self.assertEqual(result.policy.weights["temporal_fit"], 0.18)
        self.assertEqual(len(result.evidence), 3)
        self.assertEqual(result.criteria["temporal_fit"].value, 1.0)
        self.assertAlmostEqual(result.criteria["source_independence"].value, 2 / 3, places=4)
        self.assertEqual(result.criteria["primary_source_support"].value, 1.0)

    def test_news_first_published_after_anomaly_is_ineligible(self) -> None:
        late = evidence(
            "late_story",
            published_at=ANOMALY_END + timedelta(minutes=1),
            role=EvidenceRole.INDEPENDENT_REPORTING,
        )
        market = evidence(
            "market_close",
            published_at=ANOMALY_END,
            role=EvidenceRole.MARKET_DATA,
        )
        assessment = CandidateAssessment(
            anomaly_id="NVDA-2024-09-03",
            candidate_event_id="after-close-doj-story",
            anomaly_start_at=ANOMALY_START,
            anomaly_end_at=ANOMALY_END,
            as_of_at=ANOMALY_END + timedelta(hours=4),
            evidence=(late, market),
            relationship_directness=criterion(1.0, "late_story"),
            economic_plausibility=criterion(0.8, "late_story"),
            materiality=criterion(0.8, "late_story"),
            directional_consistency=criterion(1.0, "market_close"),
            novelty=criterion(0.7, "late_story"),
            market_footprint_fit=criterion(0.8, "market_close"),
        )

        result = self.scorer.score(assessment)

        self.assertFalse(result.eligible)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.classification, CausalClassification.INELIGIBLE)
        self.assertEqual(result.ignored_evidence_ids, ("late_story",))

    def test_syndicated_copies_count_as_one_lineage(self) -> None:
        copies = tuple(
            evidence(
                f"wire_copy_{index}",
                published_at=datetime(2024, 5, 30, 12, index, tzinfo=UTC),
                role=EvidenceRole.SYNDICATED_REPORT,
                lineage_id="reuters-story-123",
            )
            for index in range(10)
        )
        market = evidence(
            "market_close",
            published_at=ANOMALY_END,
            role=EvidenceRole.MARKET_DATA,
        )
        assessment = CandidateAssessment(
            anomaly_id="wire-test",
            candidate_event_id="one-wire-lineage",
            anomaly_start_at=ANOMALY_START,
            anomaly_end_at=ANOMALY_END,
            as_of_at=ANOMALY_END,
            evidence=(*copies, market),
            relationship_directness=criterion(0.8, "wire_copy_0"),
            economic_plausibility=criterion(0.8, "wire_copy_0"),
            materiality=criterion(0.7, "wire_copy_0"),
            directional_consistency=criterion(0.8, "market_close"),
            novelty=criterion(0.6, "wire_copy_0"),
            market_footprint_fit=criterion(0.8, "market_close"),
        )

        result = self.scorer.score(assessment)

        self.assertAlmostEqual(result.criteria["source_independence"].value, 1 / 3, places=4)
        self.assertEqual(result.criteria["primary_source_support"].value, 0.0)

    def test_credible_contradiction_reduces_score(self) -> None:
        baseline = self.scorer.score(hpq_assessment())
        contradiction = evidence(
            "contradictory_filing",
            published_at=datetime(2024, 5, 30, 13, 0, tzinfo=UTC),
            role=EvidenceRole.PRIMARY_SOURCE,
            stance=EvidenceStance.CONTRADICTS,
        )

        contested = self.scorer.score(
            hpq_assessment(extra_evidence=(contradiction,))
        )

        self.assertGreater(contested.contradiction_strength.value or 0, 0)
        self.assertLess(contested.score, baseline.score)
        self.assertEqual(
            contested.contradiction_strength.evidence_ids,
            ("contradictory_filing",),
        )

    def test_value_without_evidence_is_treated_as_missing(self) -> None:
        unsupported_relationship = criterion(1.0)

        result = self.scorer.score(
            hpq_assessment(relationship=unsupported_relationship)
        )

        self.assertEqual(
            result.classification,
            CausalClassification.INSUFFICIENT_EVIDENCE,
        )
        self.assertIn("relationship_directness", result.missing_criteria)
        self.assertIsNone(result.criteria["relationship_directness"].value)

    def test_criterion_using_post_cutoff_evidence_is_rejected(self) -> None:
        late_analysis = evidence(
            "future_analysis",
            published_at=ANOMALY_END + timedelta(days=1),
            role=EvidenceRole.SECONDARY_ANALYSIS,
        )
        relationship = criterion(1.0, "hp_release", "future_analysis")

        result = self.scorer.score(
            hpq_assessment(
                extra_evidence=(late_analysis,),
                relationship=relationship,
            )
        )

        self.assertIsNone(result.criteria["relationship_directness"].value)
        self.assertIn("future_analysis", result.ignored_evidence_ids)
        self.assertEqual(
            result.classification,
            CausalClassification.INSUFFICIENT_EVIDENCE,
        )

    def test_unknown_evidence_reference_is_rejected_by_schema(self) -> None:
        with self.assertRaises(ValidationError):
            hpq_assessment(relationship=criterion(1.0, "not-present"))

    def test_naive_timestamps_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evidence(
                "naive",
                published_at=datetime(2024, 5, 30, 12, 0),
                role=EvidenceRole.PRIMARY_SOURCE,
            )

    def test_weights_must_sum_to_one(self) -> None:
        invalid_weights = dict(ScorerConfig().weights)
        invalid_weights["temporal_fit"] = 0.5

        with self.assertRaises(ValueError):
            ScorerConfig(weights=invalid_weights)

    def test_config_weights_cannot_change_after_validation(self) -> None:
        config = ScorerConfig()

        with self.assertRaises(TypeError):
            config.weights["temporal_fit"] = 0.5  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
