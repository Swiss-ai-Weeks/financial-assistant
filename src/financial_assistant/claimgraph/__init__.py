"""Inspectable ClaimGraph layer for causal candidate explanations."""

from .builder import build_claim_graph
from .models import (
    AlternativeExplanation,
    ClaimGraphResult,
    EdgeKind,
    GraphEdge,
    GraphNode,
    NodeKind,
)

__all__ = [
    "AlternativeExplanation",
    "ClaimGraphResult",
    "EdgeKind",
    "GraphEdge",
    "GraphNode",
    "NodeKind",
    "build_claim_graph",
]