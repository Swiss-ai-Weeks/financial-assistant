"""
The stream the model learns on: the store's edges up to an
as-of date, as (src, dst, t, msg) in publication order, which
is the JODIE / twitter-research format the reference
implementation reads.

Node ids are dense integers assigned in order of first
appearance, so a node that first appears after the as-of date
does not exist for a model trained on that date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import torch
from torch_geometric.data import TemporalData

from financial_assistant.news_graph.extraction import FEATURE_VOCABULARY
from financial_assistant.news_graph.store import NewsGraphStore

EDGE_KINDS = ("mentions", "reports", "reports_type")

# One day in seconds: the unit of time the model sees, so the
# time encoding works on numbers of order 1-100, not 1e7.
DAY = 86400.0


def message_dim() -> int:
    return (
        len(FEATURE_VOCABULARY["event_type"])
        + len(FEATURE_VOCABULARY["direction"])
        + len(FEATURE_VOCABULARY["materiality"])
        + len(EDGE_KINDS)
    )


def encode_message(props: dict, kind: str) -> np.ndarray:
    parts = []

    for field in ("event_type", "direction", "materiality"):
        vocabulary = FEATURE_VOCABULARY[field]
        one_hot = np.zeros(len(vocabulary), dtype=np.float32)
        value = props.get(field)

        if value in vocabulary:
            one_hot[vocabulary.index(value)] = 1.0

        parts.append(one_hot)

    edge_kind = np.zeros(len(EDGE_KINDS), dtype=np.float32)

    if kind in EDGE_KINDS:
        edge_kind[EDGE_KINDS.index(kind)] = 1.0

    parts.append(edge_kind)

    return np.concatenate(parts)


@dataclass
class Stream:
    data: TemporalData
    node_ids: list[str]          # dense index -> node id
    index: dict[str, int]        # node id -> dense index
    edge_ids: np.ndarray         # dense position -> store edge_id
    epoch: datetime              # t = 0

    @property
    def num_nodes(self) -> int:
        return len(self.node_ids)

    def securities(self) -> dict[str, int]:
        return {
            node_id.split(":", 1)[1]: index
            for node_id, index in self.index.items()
            if node_id.startswith("security:")
        }


def load_stream(store: NewsGraphStore, *, end: datetime | None = None, start: datetime | None = None) -> Stream:
    edges = store.edges(start=start, end=end, kinds=EDGE_KINDS)

    if not edges:
        raise ValueError("The news graph has no edges to learn from.")

    index: dict[str, int] = {}
    node_ids: list[str] = []

    def dense(node_id: str) -> int:
        if node_id not in index:
            index[node_id] = len(node_ids)
            node_ids.append(node_id)

        return index[node_id]

    epoch = edges[0]["t"]

    src = np.empty(len(edges), dtype=np.int64)
    dst = np.empty(len(edges), dtype=np.int64)
    t = np.empty(len(edges), dtype=np.int64)
    msg = np.empty((len(edges), message_dim()), dtype=np.float32)
    edge_ids = np.empty(len(edges), dtype=np.int64)

    for position, edge in enumerate(edges):
        src[position] = dense(edge["src"])
        dst[position] = dense(edge["dst"])
        # Integer seconds, day resolution: the model does not
        # need minutes, and equal timestamps keep batches tidy.
        t[position] = int((edge["t"] - epoch).total_seconds() // DAY * DAY)
        msg[position] = encode_message(edge["props"], edge["kind"])
        edge_ids[position] = edge["edge_id"]

    data = TemporalData(
        src=torch.from_numpy(src),
        dst=torch.from_numpy(dst),
        t=torch.from_numpy(t),
        msg=torch.from_numpy(msg),
    )

    return Stream(data=data, node_ids=node_ids, index=index, edge_ids=edge_ids, epoch=epoch)
