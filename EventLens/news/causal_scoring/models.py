"""Typed contracts for causal candidate assessment.

The unit being scored is an event hypothesis for a market anomaly, not an
individual article. Articles, filings, market observations, and ontology facts
are evidence attached to that hypothesis.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]


class EvidenceRole(StrEnum):
    """Provenance role of an evidence item."""

    PRIMARY_SOURCE = "primary_source"
    INDEPENDENT_REPORTING = "independent_reporting"
    SYNDICATED_REPORT = "syndicated_report"
    SECONDARY_ANALYSIS = "secondary_analysis"
    MARKET_DATA = "market_data"


class EvidenceStance(StrEnum):
    """How an evidence item bears on the candidate event."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT_ONLY = "context_only"


class CriterionMethod(StrEnum):
    """How a criterion value was produced."""

    RULE = "rule"
    ONTOLOGY = "ontology"
    MARKET_MODEL = "market_model"
    MODEL_JUDGMENT = "model_judgment"
    HUMAN = "human"


class CausalClassification(StrEnum):
    """UI-friendly interpretation of a rank score."""

    INELIGIBLE = "ineligible"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    WEAK = "weak"
    PLAUSIBLE = "plausible"
    STRONG_CANDIDATE = "strong_candidate"


class EvidenceItem(BaseModel):
    """One traceable item used to assess an event hypothesis.

    ``lineage_id`` identifies the original reporting lineage. Ten publishers
    carrying the same wire story must therefore share one lineage ID.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_uri: HttpUrl | None = None
    published_at: AwareDatetime
    lineage_id: str = Field(min_length=1)
    role: EvidenceRole
    stance: EvidenceStance


class CriterionScore(BaseModel):
    """An auditable, normalized criterion value.

    A value without evidence is accepted by the schema so incomplete model
    output can be inspected, but the scorer treats it as missing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: UnitInterval | None = None
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    method: CriterionMethod


class CandidateAssessment(BaseModel):
    """All information available for one anomaly/event/company hypothesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anomaly_id: str = Field(min_length=1)
    candidate_event_id: str = Field(min_length=1)
    anomaly_start_at: AwareDatetime
    anomaly_end_at: AwareDatetime
    as_of_at: AwareDatetime
    evidence: tuple[EvidenceItem, ...]

    relationship_directness: CriterionScore
    economic_plausibility: CriterionScore
    materiality: CriterionScore
    directional_consistency: CriterionScore
    novelty: CriterionScore
    market_footprint_fit: CriterionScore

    @model_validator(mode="after")
    def validate_timeline_and_evidence(self) -> CandidateAssessment:
        if self.anomaly_end_at <= self.anomaly_start_at:
            raise ValueError("anomaly_end_at must be after anomaly_start_at")
        if self.as_of_at < self.anomaly_start_at:
            raise ValueError("as_of_at cannot be before anomaly_start_at")

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")

        known_ids = set(evidence_ids)
        for name in (
            "relationship_directness",
            "economic_plausibility",
            "materiality",
            "directional_consistency",
            "novelty",
            "market_footprint_fit",
        ):
            criterion = getattr(self, name)
            unknown_ids = set(criterion.evidence_ids) - known_ids
            if unknown_ids:
                unknown = ", ".join(sorted(unknown_ids))
                raise ValueError(f"{name} references unknown evidence: {unknown}")
        return self


class ScoringPolicySnapshot(BaseModel):
    """Immutable policy values needed to reproduce a returned score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    weights: dict[str, UnitInterval]
    contradiction_penalty: UnitInterval
    temporal_grace_hours: Annotated[float, Field(ge=0.0)]
    temporal_half_life_hours: Annotated[float, Field(gt=0.0)]
    independent_source_target: Annotated[int, Field(ge=1)]
    minimum_evidence_coverage: UnitInterval
    core_criterion_floor: UnitInterval
    insufficient_evidence_score_cap: Annotated[float, Field(ge=0.0, le=100.0)]
    weak_core_score_cap: Annotated[float, Field(ge=0.0, le=100.0)]
    plausible_threshold: Annotated[float, Field(ge=0.0, le=100.0)]
    strong_threshold: Annotated[float, Field(ge=0.0, le=100.0)]


class CausalScoreResult(BaseModel):
    """Auditable result returned by the deterministic scoring layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anomaly_id: str
    candidate_event_id: str
    policy: ScoringPolicySnapshot
    eligible: bool
    score: Annotated[float, Field(ge=0.0, le=100.0)]
    classification: CausalClassification
    evidence_coverage: UnitInterval
    criteria: dict[str, CriterionScore]
    contradiction_strength: CriterionScore
    missing_criteria: tuple[str, ...] = ()
    ignored_evidence_ids: tuple[str, ...] = ()
    caps_applied: tuple[str, ...] = ()
    causal_cutoff_at: AwareDatetime
    evidence: tuple[EvidenceItem, ...]
