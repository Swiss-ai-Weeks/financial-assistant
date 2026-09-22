"""
What the trained model says about the stream.

Replayed from the start with an empty memory, every edge is
scored BEFORE the model sees it: the probability it was
expected given everything published earlier. Surprise is one
minus that. Per security and day the surprises are averaged
and the day's largest kept, and the memory vector's distance
from its own recent average is the drift.

At the end of the replay the model is asked, for each
security, which of the recently active nodes it expects an
edge to next: the dashed red edges of the graph view.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import torch
from .dataset import DAY, Stream
from .model import TemporalGraphNetwork

# Drift compares today's memory with an exponential average of
# the previous days'; this is its horizon in sessions.
DRIFT_HALF_LIFE_DAYS = 20

# How far back a node must have been active to be a candidate
# for a predicted edge, and how many predictions are kept.
CANDIDATE_DAYS = 90
PREDICTIONS_PER_SECURITY = 15


@dataclass
class Scores:
    edge_probs: list[tuple[int, float]]           # (store edge_id, prob)
    daily: list[tuple]                             # (ticker, day, surprise_mean, surprise_max, drift, edges)
    predictions: list[tuple]                       # (ticker, node_id, as_of, prob)


@torch.no_grad()
def score(model: TemporalGraphNetwork, stream: Stream, *, batch_size: int = 200) -> Scores:
    model.eval()
    model.reset()

    data = stream.data.to(model.device)
    securities = stream.securities()                       # ticker -> dense index
    by_index = {index: ticker for ticker, index in securities.items()}

    edge_probs: list[tuple[int, float]] = []
    surprises: dict[tuple[str, int], list[float]] = defaultdict(list)

    # Drift bookkeeping per security: the EMA of past memories.
    ema: dict[str, torch.Tensor] = {}
    drift: dict[tuple[str, int], float] = {}
    alpha = 1 - 0.5 ** (1 / DRIFT_HALF_LIFE_DAYS)

    def close_day(day: int) -> None:
        memory, _ = model.memory(torch.tensor(list(by_index), device=model.device))

        for row, index in enumerate(by_index):
            ticker = by_index[index]
            vector = memory[row]

            if ticker in ema:
                cosine = torch.nn.functional.cosine_similarity(vector, ema[ticker], dim=0)
                drift[(ticker, day)] = float(1 - cosine)
                ema[ticker] = (1 - alpha) * ema[ticker] + alpha * vector
            else:
                ema[ticker] = vector.clone()

    # Events are processed day by day (they are sorted by t, so
    # a day is a contiguous slice), in chunks of `batch_size`
    # within the day, and the day is closed once all of it has
    # been observed: the drift is the memory at the day's end.
    days = (data.t // DAY).long()
    boundaries = torch.cat([torch.tensor([0], device=days.device), (days[1:] != days[:-1]).nonzero().flatten() + 1, torch.tensor([len(days)], device=days.device)])

    for first, last in zip(boundaries[:-1].tolist(), boundaries[1:].tolist()):
        day = int(days[first].item())

        for lo in range(first, last, batch_size):
            hi = min(lo + batch_size, last)
            src, dst, t, msg = data.src[lo:hi], data.dst[lo:hi], data.t[lo:hi], data.msg[lo:hi]

            n_id = torch.cat([src, dst]).unique()
            z, _ = model.embed(n_id, data.t, data.msg)
            prob = model.link_pred(z[model.assoc[src]], z[model.assoc[dst]]).sigmoid().cpu().numpy().ravel()

            for offset, p in enumerate(prob):
                edge_probs.append((int(stream.edge_ids[lo + offset]), float(p)))

                ticker = by_index.get(int(src[offset]))

                if ticker is not None:
                    surprises[(ticker, day)].append(1.0 - float(p))

            model.observe(src, dst, t, msg)

        close_day(day)

    daily = [
        (
            ticker,
            (stream.epoch + timedelta(days=day)).date().isoformat(),
            float(np.mean(values)),
            float(np.max(values)),
            drift.get((ticker, day)),
            len(values),
        )
        for (ticker, day), values in sorted(surprises.items())
    ]

    return Scores(edge_probs=edge_probs, daily=daily, predictions=_predict(model, stream, data, securities))


@torch.no_grad()
def _predict(model, stream: Stream, data, securities: dict[str, int]) -> list[tuple]:
    """The edges each security is most likely to have next."""

    last_t = float(data.t[-1].item())
    as_of = (stream.epoch + timedelta(seconds=last_t)).date().isoformat()

    recent = data.t >= last_t - CANDIDATE_DAYS * DAY
    candidates = data.dst[recent].unique()

    if candidates.numel() == 0 or not securities:
        return []

    rows: list[tuple] = []

    for ticker, index in securities.items():
        src = torch.full((candidates.numel(),), index, dtype=torch.long, device=model.device)

        n_id = torch.cat([src, candidates]).unique()
        z, _ = model.embed(n_id, data.t, data.msg)
        prob = model.link_pred(z[model.assoc[src]], z[model.assoc[candidates]]).sigmoid().cpu().numpy().ravel()

        order = np.argsort(-prob)[:PREDICTIONS_PER_SECURITY]

        rows.extend(
            (ticker, stream.node_ids[int(candidates[i])], as_of, float(prob[i]))
            for i in order
        )

    return rows
