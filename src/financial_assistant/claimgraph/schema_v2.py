from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeKind(StrEnum):
    ANOMALY = "anomaly"

    SOURCE = "source"
    DOCUMENT = "document"

    CLAIM = "claim"
    HYPOTHESIS = "hypothesis"

    EVIDENCE_REQUIREMENT = "evidence_requirement"

    OBSERVATION = "observation"
    CALCULATION = "calculation"
    INFERENCE = "inference"

    MODEL_RUN = "model_run"

    MISSING_EVIDENCE = "missing_evidence"


class EdgeKind(StrEnum):
    TRIGGERED = "triggered"
    CANDIDATE_EXPLANATION_FOR = "candidate_explanation_for"

    PUBLISHED_BY = "published_by"
    EXTRACTED_FROM = "extracted_from"

    PRODUCED_BY = "produced_by"

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    WEAKENS = "weakens"
    CONTEXT_FOR = "context_for"

    REQUIRES = "requires"

    CALCULATED_FROM = "calculated_from"
    DERIVED_FROM = "derived_from"

    COMPETES_WITH = "competes_with"


class GraphNode(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    node_id: str = Field(min_length=1)
    kind: NodeKind

    label: str = Field(min_length=1)

    data: dict[str, Any] = Field(
        default_factory=dict
    )


class GraphEdge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    edge_id: str = Field(min_length=1)

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)

    kind: EdgeKind

    data: dict[str, Any] = Field(
        default_factory=dict
    )


class InvestigationGraph(BaseModel):
    """
    Stable backend -> frontend contract.

    Semantic processing happens before this.
    React should only need nodes and edges.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    schema_version: str = "0.2"

    investigation_id: str = Field(min_length=1)
    anomaly_id: str = Field(min_length=1)

    ticker: str = Field(min_length=1)

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
