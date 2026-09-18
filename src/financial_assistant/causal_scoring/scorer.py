"""Deterministic aggregation for causal candidate ranking.

Language models or domain services may propose the semantic criterion values,
but this module owns cut-off enforcement, source-lineage handling, penalties,
weighting, score caps, and the final traceable result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose
from types import MappingProxyType
from typing import Mapping

from .models import (
    CandidateAssessment,
    CausalClassification,
    CausalScoreResult,
    CriterionMethod,
    CriterionScore,
    EvidenceItem,
    EvidenceRole,
    EvidenceStance,
    ScoringPolicySnapshot,
)


DEFAULT_WEIGHTS: dict[str, float] = {
    "temporal_fit": 0.18,
    "relationship_directness": 0.14,
    "economic_plausibility": 0.14,
    "materiality": 0.12,
    "directional_consistency": 0.10,
    "source_independence": 0.08,
    "primary_source_support": 0.08,
    "novelty": 0.06,
    "market_footprint_fit": 0.10,
}

CORE_CRITERIA = (
    "temporal_fit",
    "relationship_directness",
    "economic_plausibility",
)

ROLE_QUALITY: dict[EvidenceRole, float] = {
    EvidenceRole.PRIMARY_SOURCE: 1.0,
    EvidenceRole.INDEPENDENT_REPORTING: 0.8,
    EvidenceRole.SECONDARY_ANALYSIS: 0.5,
    EvidenceRole.SYNDICATED_REPORT: 0.35,
    EvidenceRole.MARKET_DATA: 0.0,
}


@dataclass(frozen=True)
class ScorerConfig:
    """Configuration for a transparent rank score.

    These defaults are starting heuristics, not calibrated causal
    probabilities. Teams should version and tune them against labelled cases.
    """

    policy_version: str = "causal-candidate-v1"
    weights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    contradiction_penalty: float = 0.25
    temporal_grace_hours: float = 24.0
    temporal_half_life_hours: float = 48.0
    independent_source_target: int = 3
    minimum_evidence_coverage: float = 0.70
    core_criterion_floor: float = 0.25
    insufficient_evidence_score_cap: float = 60.0
    weak_core_score_cap: float = 40.0
    plausible_threshold: float = 65.0
    strong_threshold: float = 85.0

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version cannot be empty")
        if set(self.weights) != set(DEFAULT_WEIGHTS):
            raise ValueError("weights must contain exactly the supported criteria")
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("weights cannot be negative")
        if not isclose(sum(self.weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("weights must sum to 1.0")
        if not 0 <= self.contradiction_penalty <= 1:
            raise ValueError("contradiction_penalty must be between 0 and 1")
        if self.temporal_grace_hours < 0 or self.temporal_half_life_hours <= 0:
            raise ValueError("temporal grace must be non-negative and half-life positive")
        if self.independent_source_target < 1:
            raise ValueError("independent_source_target must be at least 1")
        if not 0 <= self.minimum_evidence_coverage <= 1:
            raise ValueError("minimum_evidence_coverage must be between 0 and 1")
        if not 0 <= self.core_criterion_floor <= 1:
            raise ValueError("core_criterion_floor must be between 0 and 1")
        if not 0 <= self.insufficient_evidence_score_cap <= 100:
            raise ValueError("insufficient_evidence_score_cap must be within 0..100")
        if not 0 <= self.weak_core_score_cap <= 100:
            raise ValueError("weak_core_score_cap must be within 0..100")
        if not 0 <= self.plausible_threshold <= self.strong_threshold <= 100:
            raise ValueError("classification thresholds must be ordered within 0..100")
        object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))


class CausalCandidateScorer:
    """Rank event hypotheses while preserving evidence and uncertainty."""

    def __init__(self, config: ScorerConfig | None = None) -> None:
        self.config = config or ScorerConfig()

    def score(self, assessment: CandidateAssessment) -> CausalScoreResult:
        """Score one event hypothesis at a strict, reproducible cut-off."""

        causal_cutoff = min(assessment.as_of_at, assessment.anomaly_end_at)
        available_evidence = tuple(
            item for item in assessment.evidence if item.published_at <= causal_cutoff
        )
        ignored_evidence_ids = tuple(
            sorted(
                item.evidence_id
                for item in assessment.evidence
                if item.published_at > causal_cutoff
            )
        )

        supporting_news = tuple(
            item
            for item in available_evidence
            if item.stance is EvidenceStance.SUPPORTS
            and item.role is not EvidenceRole.MARKET_DATA
        )

        supplied = self._sanitize_supplied_criteria(
            assessment=assessment,
            available_evidence=available_evidence,
        )

        if not supporting_news:
            criteria = {
                "temporal_fit": self._rule_score(
                    value=0.0,
                    rationale="No supporting public-news evidence existed by the causal cutoff.",
                ),
                **supplied,
                "source_independence": self._rule_score(
                    value=0.0,
                    rationale="No supporting reporting lineage existed by the causal cutoff.",
                ),
                "primary_source_support": self._rule_score(
                    value=0.0,
                    rationale="No supporting primary source existed by the causal cutoff.",
                ),
            }
            return CausalScoreResult(
                anomaly_id=assessment.anomaly_id,
                candidate_event_id=assessment.candidate_event_id,
                policy=self._policy_snapshot(),
                eligible=False,
                score=0.0,
                classification=CausalClassification.INELIGIBLE,
                evidence_coverage=0.0,
                criteria=criteria,
                contradiction_strength=self._rule_score(
                    value=0.0,
                    rationale="Contradictions are not scored without an eligible candidate.",
                ),
                missing_criteria=tuple(
                    name for name, criterion in criteria.items() if criterion.value is None
                ),
                ignored_evidence_ids=ignored_evidence_ids,
                causal_cutoff_at=causal_cutoff,
                evidence=assessment.evidence,
            )

        temporal_fit = self._temporal_fit(assessment, supporting_news)
        source_independence = self._source_independence(supporting_news)
        primary_support = self._primary_source_support(supporting_news)
        contradiction = self._contradiction_strength(available_evidence, supporting_news)

        criteria = {
            "temporal_fit": temporal_fit,
            "relationship_directness": supplied["relationship_directness"],
            "economic_plausibility": supplied["economic_plausibility"],
            "materiality": supplied["materiality"],
            "directional_consistency": supplied["directional_consistency"],
            "source_independence": source_independence,
            "primary_source_support": primary_support,
            "novelty": supplied["novelty"],
            "market_footprint_fit": supplied["market_footprint_fit"],
        }

        missing_criteria = tuple(
            name for name, criterion in criteria.items() if criterion.value is None
        )
        coverage = sum(
            self.config.weights[name]
            for name, criterion in criteria.items()
            if criterion.value is not None
        )
        base_score = sum(
            self.config.weights[name] * (criterion.value or 0.0)
            for name, criterion in criteria.items()
        )
        score = 100.0 * max(
            0.0,
            base_score
            - self.config.contradiction_penalty * (contradiction.value or 0.0),
        )

        caps_applied: list[str] = []
        missing_core = any(criteria[name].value is None for name in CORE_CRITERIA)
        weak_core = any(
            criteria[name].value is not None
            and criteria[name].value < self.config.core_criterion_floor
            for name in CORE_CRITERIA
        )

        if coverage < self.config.minimum_evidence_coverage:
            score = min(score, self.config.insufficient_evidence_score_cap)
            caps_applied.append("insufficient_evidence_coverage")
        if weak_core:
            score = min(score, self.config.weak_core_score_cap)
            caps_applied.append("weak_core_criterion")

        if missing_core or coverage < self.config.minimum_evidence_coverage:
            classification = CausalClassification.INSUFFICIENT_EVIDENCE
        elif score >= self.config.strong_threshold:
            classification = CausalClassification.STRONG_CANDIDATE
        elif score >= self.config.plausible_threshold:
            classification = CausalClassification.PLAUSIBLE
        else:
            classification = CausalClassification.WEAK

        return CausalScoreResult(
            anomaly_id=assessment.anomaly_id,
            candidate_event_id=assessment.candidate_event_id,
            policy=self._policy_snapshot(),
            eligible=True,
            score=round(score, 1),
            classification=classification,
            evidence_coverage=round(coverage, 3),
            criteria=criteria,
            contradiction_strength=contradiction,
            missing_criteria=missing_criteria,
            ignored_evidence_ids=ignored_evidence_ids,
            caps_applied=tuple(caps_applied),
            causal_cutoff_at=causal_cutoff,
            evidence=assessment.evidence,
        )

    def _policy_snapshot(self) -> ScoringPolicySnapshot:
        return ScoringPolicySnapshot(
            version=self.config.policy_version,
            weights=dict(self.config.weights),
            contradiction_penalty=self.config.contradiction_penalty,
            temporal_grace_hours=self.config.temporal_grace_hours,
            temporal_half_life_hours=self.config.temporal_half_life_hours,
            independent_source_target=self.config.independent_source_target,
            minimum_evidence_coverage=self.config.minimum_evidence_coverage,
            core_criterion_floor=self.config.core_criterion_floor,
            insufficient_evidence_score_cap=(
                self.config.insufficient_evidence_score_cap
            ),
            weak_core_score_cap=self.config.weak_core_score_cap,
            plausible_threshold=self.config.plausible_threshold,
            strong_threshold=self.config.strong_threshold,
        )

    def _sanitize_supplied_criteria(
        self,
        assessment: CandidateAssessment,
        available_evidence: tuple[EvidenceItem, ...],
    ) -> dict[str, CriterionScore]:
        available_ids = {item.evidence_id for item in available_evidence}
        sanitized: dict[str, CriterionScore] = {}

        for name in (
            "relationship_directness",
            "economic_plausibility",
            "materiality",
            "directional_consistency",
            "novelty",
            "market_footprint_fit",
        ):
            criterion: CriterionScore = getattr(assessment, name)
            referenced_ids = set(criterion.evidence_ids)
            unavailable_ids = referenced_ids - available_ids

            if criterion.value is None:
                sanitized[name] = criterion
            elif not referenced_ids:
                sanitized[name] = CriterionScore(
                    value=None,
                    rationale=(
                        "Criterion was rejected because its value had no traceable evidence. "
                        f"Original rationale: {criterion.rationale}"
                    ),
                    method=criterion.method,
                )
            elif unavailable_ids:
                unavailable = ", ".join(sorted(unavailable_ids))
                sanitized[name] = CriterionScore(
                    value=None,
                    rationale=(
                        "Criterion was rejected because it used evidence unavailable at the "
                        f"causal cutoff: {unavailable}. Original rationale: {criterion.rationale}"
                    ),
                    evidence_ids=tuple(sorted(referenced_ids & available_ids)),
                    method=criterion.method,
                )
            else:
                sanitized[name] = criterion

        return sanitized

    def _temporal_fit(
        self,
        assessment: CandidateAssessment,
        supporting_news: tuple[EvidenceItem, ...],
    ) -> CriterionScore:
        first_public = min(item.published_at for item in supporting_news)
        hours_before_start = max(
            0.0,
            (assessment.anomaly_start_at - first_public).total_seconds() / 3600.0,
        )

        if hours_before_start <= self.config.temporal_grace_hours:
            value = 1.0
        else:
            decaying_hours = hours_before_start - self.config.temporal_grace_hours
            value = 0.5 ** (decaying_hours / self.config.temporal_half_life_hours)

        return self._rule_score(
            value=round(value, 4),
            rationale=(
                f"First supporting public evidence appeared at {first_public.isoformat()}; "
                f"{hours_before_start:.1f} hours before the anomaly window."
            ),
            evidence_ids=(
                min(supporting_news, key=lambda item: item.published_at).evidence_id,
            ),
        )

    def _source_independence(
        self,
        supporting_news: tuple[EvidenceItem, ...],
    ) -> CriterionScore:
        lineages = {item.lineage_id for item in supporting_news}
        value = min(1.0, len(lineages) / self.config.independent_source_target)
        return self._rule_score(
            value=round(value, 4),
            rationale=(
                f"Found {len(lineages)} distinct supporting reporting lineage(s); "
                f"target is {self.config.independent_source_target}."
            ),
            evidence_ids=tuple(sorted(item.evidence_id for item in supporting_news)),
        )

    def _primary_source_support(
        self,
        supporting_news: tuple[EvidenceItem, ...],
    ) -> CriterionScore:
        primary_ids = tuple(
            sorted(
                item.evidence_id
                for item in supporting_news
                if item.role is EvidenceRole.PRIMARY_SOURCE
            )
        )
        return self._rule_score(
            value=1.0 if primary_ids else 0.0,
            rationale=(
                "At least one supporting primary source is available."
                if primary_ids
                else "No supporting primary source is available."
            ),
            evidence_ids=primary_ids,
        )

    def _contradiction_strength(
        self,
        available_evidence: tuple[EvidenceItem, ...],
        supporting_news: tuple[EvidenceItem, ...],
    ) -> CriterionScore:
        contradictory_news = tuple(
            item
            for item in available_evidence
            if item.stance is EvidenceStance.CONTRADICTS
            and item.role is not EvidenceRole.MARKET_DATA
        )

        support_weight = sum(self._lineage_quality(supporting_news).values())
        contradiction_weight = sum(self._lineage_quality(contradictory_news).values())
        value = min(1.0, contradiction_weight / support_weight) if support_weight else 0.0

        return self._rule_score(
            value=round(value, 4),
            rationale=(
                f"Contradictory lineage quality is {contradiction_weight:.2f} versus "
                f"{support_weight:.2f} for supporting lineages."
            ),
            evidence_ids=tuple(sorted(item.evidence_id for item in contradictory_news)),
        )

    @staticmethod
    def _lineage_quality(items: tuple[EvidenceItem, ...]) -> dict[str, float]:
        quality_by_lineage: dict[str, float] = {}
        for item in items:
            quality_by_lineage[item.lineage_id] = max(
                quality_by_lineage.get(item.lineage_id, 0.0),
                ROLE_QUALITY[item.role],
            )
        return quality_by_lineage

    @staticmethod
    def _rule_score(
        *,
        value: float,
        rationale: str,
        evidence_ids: tuple[str, ...] = (),
    ) -> CriterionScore:
        return CriterionScore(
            value=value,
            rationale=rationale,
            evidence_ids=evidence_ids,
            method=CriterionMethod.RULE,
        )
