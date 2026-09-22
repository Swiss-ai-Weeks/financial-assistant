"""
The temporal news graph of the book.

Every article the wire brings is read once by the model and
becomes timestamped edges between the securities it concerns,
the entities it names and the canonical event it reports:

    security --mentions(t)--> entity
    security --reports(t)-->  event   (typed: earnings, M&A, ...)

The graph is a stream of events in publication order. That is
what the WIRE page shows, what GraphRAG queries as of a date,
and what the temporal graph network (tgn/) learns on.
"""

from .models import (
    EVENT_TYPES,
    Edge,
    EventType,
    Extraction,
    Node,
    NodeKind,
)
from .store import NewsGraphStore

__all__ = [
    "EVENT_TYPES",
    "Edge",
    "EventType",
    "Extraction",
    "NewsGraphStore",
    "Node",
    "NodeKind",
]
