"""
Training as in the paper: the stream is split by time, never
shuffled (the first 70% to learn, the next 15% to choose the
epoch, the last 15% to report), and the task is to tell each
real edge from a sampled one that did not happen.

Memory is updated only after a batch has been predicted, so a
prediction never sees its own outcome.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch_geometric.loader import TemporalDataLoader

from .dataset import Stream
from .model import Hyperparameters, TemporalGraphNetwork


def roc_auc_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """AUC as the Mann-Whitney statistic, ties counted half."""

    positives = y_score[y_true == 1]
    negatives = y_score[y_true == 0]

    if len(positives) == 0 or len(negatives) == 0:
        return float("nan")

    greater = (positives[:, None] > negatives[None, :]).mean()
    equal = (positives[:, None] == negatives[None, :]).mean()

    return float(greater + 0.5 * equal)


def average_precision_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
    order = np.argsort(-y_score, kind="stable")
    hits = y_true[order] == 1

    if not hits.any():
        return float("nan")

    precision = np.cumsum(hits) / np.arange(1, len(hits) + 1)

    return float(precision[hits].mean())


@dataclass
class Report:
    epochs: int
    best_epoch: int
    val_ap: float
    val_auc: float
    test_ap: float
    test_auc: float
    seconds: float
    events: int
    nodes: int


def _run_epoch(model: TemporalGraphNetwork, loader, data, *, optimizer=None, seed: int = 0):
    with torch.set_grad_enabled(optimizer is not None):
        return _pass(model, loader, data, optimizer=optimizer, seed=seed)


def _pass(model: TemporalGraphNetwork, loader, data, *, optimizer=None, seed: int = 0):
    """
    One pass over `loader`. With an optimizer it trains;
    without, it evaluates. Either way memory advances with the
    stream, so the caller resets before the first split and
    carries state between splits.
    """

    training = optimizer is not None
    model.train(training)

    generator = torch.Generator(device=model.device).manual_seed(seed)
    total_loss = 0.0
    aps, aucs = [], []

    for batch in loader:
        batch = batch.to(model.device)
        src, pos_dst, t, msg = batch.src, batch.dst, batch.t, batch.msg

        neg_dst = torch.randint(0, model.num_nodes, (src.size(0),), dtype=torch.long, device=model.device, generator=generator)

        n_id = torch.cat([src, pos_dst, neg_dst]).unique()
        z, _ = model.embed(n_id, data.t, data.msg)

        pos_out = model.link_pred(z[model.assoc[src]], z[model.assoc[pos_dst]])
        neg_out = model.link_pred(z[model.assoc[src]], z[model.assoc[neg_dst]])

        if training:
            loss = torch.nn.functional.binary_cross_entropy_with_logits(pos_out, torch.ones_like(pos_out))
            loss += torch.nn.functional.binary_cross_entropy_with_logits(neg_out, torch.zeros_like(neg_out))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            model.memory.detach()
            total_loss += float(loss) * batch.num_events
        else:
            y_pred = torch.cat([pos_out, neg_out], dim=0).sigmoid().detach().cpu().numpy().ravel()
            y_true = np.concatenate([np.ones(pos_out.size(0)), np.zeros(neg_out.size(0))])
            aps.append(average_precision_score(y_true, y_pred))
            aucs.append(roc_auc_score(y_true, y_pred))

        model.observe(src, pos_dst, t, msg)

    if training:
        return total_loss / max(1, data.num_events)

    return float(np.mean(aps)) if aps else float("nan"), float(np.mean(aucs)) if aucs else float("nan")


def train(
    stream: Stream,
    *,
    hp: Hyperparameters = Hyperparameters(),
    device: torch.device = torch.device("cpu"),
    checkpoint: Path | None = None,
    log=print,
    seed: int = 0,
) -> tuple[TemporalGraphNetwork, Report]:
    torch.manual_seed(seed)

    data = stream.data.to(device)
    train_data, val_data, test_data = data.train_val_test_split(val_ratio=0.15, test_ratio=0.15)

    train_loader = TemporalDataLoader(train_data, batch_size=hp.batch_size)
    val_loader = TemporalDataLoader(val_data, batch_size=hp.batch_size)
    test_loader = TemporalDataLoader(test_data, batch_size=hp.batch_size)

    model = TemporalGraphNetwork(stream.num_nodes, data.msg.size(-1), hp, device)
    optimizer = torch.optim.Adam(model.parameters_to_train(), lr=hp.learning_rate)

    started = time.perf_counter()
    best = (-1.0, 0, None, (float("nan"), float("nan")))

    for epoch in range(1, hp.epochs + 1):
        model.reset()
        loss = _run_epoch(model, train_loader, data, optimizer=optimizer, seed=seed + epoch)
        val_ap, val_auc = _run_epoch(model, val_loader, data)
        test_ap, test_auc = _run_epoch(model, test_loader, data)

        log(f"epoch {epoch:02d}  loss {loss:.4f}  val AP {val_ap:.4f} AUC {val_auc:.4f}  test AP {test_ap:.4f} AUC {test_auc:.4f}")

        if val_ap > best[0]:
            best = (val_ap, epoch, {k: (v.clone() if hasattr(v, "clone") else v) for k, v in _flat_state(model).items()}, (val_auc, test_ap, test_auc))

    _load_flat_state(model, best[2])

    report = Report(
        epochs=hp.epochs,
        best_epoch=best[1],
        val_ap=best[0],
        val_auc=best[3][0],
        test_ap=best[3][1],
        test_auc=best[3][2],
        seconds=round(time.perf_counter() - started, 1),
        events=int(data.num_events),
        nodes=stream.num_nodes,
    )

    if checkpoint is not None:
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        torch.save({**model.snapshot(), "report": asdict(report), "node_ids": stream.node_ids}, checkpoint)

    return model, report


def _flat_state(model: TemporalGraphNetwork) -> dict:
    return {
        f"{name}.{key}": value
        for name, module in (("memory", model.memory), ("gnn", model.gnn), ("link_pred", model.link_pred))
        for key, value in module.state_dict().items()
    }


def _load_flat_state(model: TemporalGraphNetwork, flat: dict) -> None:
    for name, module in (("memory", model.memory), ("gnn", model.gnn), ("link_pred", model.link_pred)):
        module.load_state_dict({k[len(name) + 1:]: v for k, v in flat.items() if k.startswith(name + ".")})
