from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ClaimType(StrEnum):
    REPORTED_FACT = "reported_fact"
    ATTRIBUTED_CLAIM = "attributed_claim"
    FORECAST = "forecast"
    INTERPRETATION = "interpretation"


class RelationKind(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    WEAKENS = "weakens"
    CONTEXT_FOR = "context_for"
    UNRELATED = "unrelated"


class ArgumentNodeKind(StrEnum):
    CLAIM = "claim"
    HYPOTHESIS = "hypothesis"
    OBSERVATION = "observation"
    CALCULATION = "calculation"
    INFERENCE = "inference"


class ModelOperation(StrEnum):
    CLAIM_EXTRACTION = "claim_extraction"
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    HYPOTHESIS_AUDIT = "hypothesis_audit"
    RELATION_ASSESSMENT = "relation_assessment"
    CAUSAL_TRIAGE = "causal_triage"
    FUNDAMENTAL_TEST_SELECTION = "fundamental_test_selection"
    INFERENCE = "inference"


class AnomalyEvent(BaseModel):
    """
    Quantitative attention event produced upstream.

    The anomaly says that something deserves investigation.
    It does not itself assert why the market move occurred.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    anomaly_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    detected_at: datetime

    anomaly_type: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    severity: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    # Other securities directly involved in the
    # anomaly. For a pair anomaly, ticker remains
    # the primary routing/display entity while the
    # second leg is preserved here.
    related_entities: tuple[str, ...] = ()

    # Quantitative detector details that should
    # remain inspectable but are not universal
    # properties of every anomaly type.
    metadata: dict[str, float | int | str] = Field(
        default_factory=dict
    )


class SourceDocument(BaseModel):
    """
    Normalised document retrieved from news, company IR,
    SEC/EDGAR or another source.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    document_id: str = Field(min_length=1)

    title: str = Field(min_length=1)
    publisher: str | None = None
    url: HttpUrl

    published_at: datetime | None = None

    # True when the source exposed only a calendar
    # date and no publication time. In that case
    # published_at is normalized to midnight only as
    # a date carrier; midnight must NOT be interpreted
    # as the actual publication time.
    published_date_only: bool = False

    retrieved_at: datetime

    text: str = Field(min_length=1)

    # Syndicated copies can share one information lineage.
    lineage_id: str | None = None


class ModelRun(BaseModel):
    """
    Execution provenance for one model operation.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: str = Field(min_length=1)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)

    operation: ModelOperation
    prompt_version: str = Field(min_length=1)

    created_at: datetime


class ExtractedClaim(BaseModel):
    """
    Atomic proposition extracted from a document.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    claim_id: str = Field(min_length=1)

    text: str = Field(min_length=1)
    claim_type: ClaimType

    document_id: str = Field(min_length=1)

    # Exact supporting source span.
    source_quote: str = Field(min_length=1)

    # Execution provenance.
    model_run_id: str = Field(min_length=1)


class Hypothesis(BaseModel):
    """
    Candidate explanation for the anomaly.

    A hypothesis is not evidence. Any unobserved facts
    required for the explanation are recorded explicitly
    as assumptions.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    hypothesis_id: str = Field(min_length=1)
    text: str = Field(min_length=1)

    assumptions: tuple[str, ...] = ()

    model_run_id: str = Field(min_length=1)


class HypothesisAudit(BaseModel):
    """
    Audit of the unsupported premises behind a
    candidate hypothesis.

    This is separate from hypothesis generation so
    execution provenance remains explicit.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    audit_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)

    assumptions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()

    model_run_id: str = Field(min_length=1)


class RelationshipAssessment(BaseModel):
    """
    Epistemic relationship between two analytical
    objects.

    Examples:
      claim -> hypothesis
      inference -> hypothesis
      observation -> hypothesis

    The relationship is contextual: the same claim
    may support one hypothesis and contradict another.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    assessment_id: str = Field(min_length=1)

    source_kind: ArgumentNodeKind
    source_id: str = Field(min_length=1)

    target_kind: ArgumentNodeKind
    target_id: str = Field(min_length=1)

    relation: RelationKind

    strength: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    rationale: str = Field(min_length=1)

    assumptions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()

    model_run_id: str = Field(min_length=1)


class EvidenceRequirement(BaseModel):
    """
    Information needed to discriminate between hypotheses.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    requirement_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)

    question: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    model_run_id: str = Field(min_length=1)


class Observation(BaseModel):
    """
    Directly observed value, such as an XBRL fact.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    observation_id: str = Field(min_length=1)

    name: str = Field(min_length=1)

    value: float
    unit: str | None = None

    source_document_id: str = Field(min_length=1)


class Calculation(BaseModel):
    """
    Deterministic arithmetic performed outside the LLM.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    calculation_id: str = Field(min_length=1)

    label: str = Field(min_length=1)
    expression: str = Field(min_length=1)

    input_observation_ids: tuple[str, ...]

    value: float
    unit: str | None = None


class Inference(BaseModel):
    """
    Interpretive conclusion derived from claims,
    observations or calculations.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    inference_id: str = Field(min_length=1)

    text: str = Field(min_length=1)

    derived_from_ids: tuple[str, ...]

    model_run_id: str = Field(min_length=1)


class InvestigationState(BaseModel):
    """
    Typed analytical state for one investigation.

    This is the semantic input to the ClaimGraph
    builder. It is deliberately independent from
    ReactFlow and the graph rendering format.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    investigation_id: str = Field(
        min_length=1
    )

    anomaly: AnomalyEvent

    documents: tuple[
        SourceDocument,
        ...
    ] = ()

    model_runs: tuple[
        ModelRun,
        ...
    ] = ()

    claims: tuple[
        ExtractedClaim,
        ...
    ] = ()

    hypotheses: tuple[
        Hypothesis,
        ...
    ] = ()

    hypothesis_audits: tuple[
        HypothesisAudit,
        ...
    ] = ()

    relationship_assessments: tuple[
        RelationshipAssessment,
        ...
    ] = ()

    evidence_requirements: tuple[
        EvidenceRequirement,
        ...
    ] = ()

    observations: tuple[
        Observation,
        ...
    ] = ()

    calculations: tuple[
        Calculation,
        ...
    ] = ()

    inferences: tuple[
        Inference,
        ...
    ] = ()



