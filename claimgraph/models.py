"""Typed contracts for the inspectable ClaimGraph layer.

ClaimGraph does not rescore causal candidates.

It takes the output of causal_scoring and turns the leading analytical
explanation into an inspectable graph of:

claim
→ subclaims
→ evidence / counter-evidence
→ sources
→ missing evidence

This is deliberately small for the hackathon MVP.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from financial_assistant.causal_scoring.models import CausalClassification


class NodeKind(StrEnum):
    PRIMARY_CLAIM = "primary_claim"
    SUBCLAIM = "subclaim"
    EVIDENCE = "evidence"
    COUNTER_EVIDENCE = "counter_evidence"
    SOURCE = "source"
    MISSING_EVIDENCE = "missing_evidence"
    ALTERNATIVE_EXPLANATION = "alternative_explanation"


class EdgeKind(StrEnum):
    DECOMPOSES_TO = "decomposes_to"
    SUPPORTED_BY = "supported_by"
    CONTRADICTED_BY = "contradicted_by"
    CONTEXT_FROM = "context_from"
    SOURCED_FROM = "sourced_from"
    MISSING_SUPPORT_FOR = "missing_support_for"
    COMPETES_WITH = "competes_with"


class ClaimAssessment(StrEnum):
    STRONG = "strong"
    SUPPORTED = "supported"
    WEAK = "weak"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INELIGIBLE = "ineligible"


class GraphNode(BaseModel):
    """A node exposed to the inspection UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    kind: NodeKind
    label: str = Field(min_length=1)

    assessment: ClaimAssessment | None = None

    # Normalized 0..1 value when the node maps to a causal criterion.
    score: Annotated[float, Field(ge=0.0, le=1.0)] | None = None

    rationale: str | None = None

    # Links back into causal_scoring provenance.
    criterion_name: str | None = None
    evidence_ids: tuple[str, ...] = ()

    # Source fields are populated only for source/evidence nodes.
    source_name: str | None = None
    source_uri: HttpUrl | None = None

    # Useful for UI/debugging without introducing more domain classes yet.
    method: str | None = None


class GraphEdge(BaseModel):
    """A typed relationship between two graph nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    kind: EdgeKind


class AlternativeExplanation(BaseModel):
    """A competing causal candidate retained for human inspection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_event_id: str
    label: str
    score: Annotated[float, Field(ge=0.0, le=100.0)]
    classification: CausalClassification


class ClaimGraphResult(BaseModel):
    """Serializable output consumed by the dashboard."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "0.1"

    anomaly_id: str
    candidate_event_id: str

    primary_claim_id: str

    causal_score: Annotated[float, Field(ge=0.0, le=100.0)]
    causal_classification: CausalClassification

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    alternatives: tuple[AlternativeExplanation, ...] = ()