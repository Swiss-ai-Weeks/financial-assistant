"""
The news graph of the book and its temporal graph network.

    make wire-ingest      read every unread article of the book into the graph
    make wire-train       train the TGN on the graph (chronological split)
    make wire-score       score every edge, every security-day, next week's expected edges
    make wire-evaluate    do surprising days precede price shocks more than ordinary days?
    make wire             keep the graph current: refresh news, ingest, score, every N minutes

    python scripts/wire.py ingest --limit 200        # a first look
    python scripts/wire.py train --epochs 30 --device cuda
    python scripts/wire.py score --as-of 2026-06-30   # a point-in-time replay

Reading articles is one Nemotron call each: run it on the GPU
box against the local vLLM (LLM_PROFILE=local). Against a
hosted gateway a call takes minutes, and the script says so.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, time as time_of_day, timedelta, timezone
from pathlib import Path

from financial_assistant.api.config import get_settings
from financial_assistant.api.dependencies import (
    get_market_repository,
    get_model_registry,
    get_news_archive,
    get_news_graph_store,
    get_news_repository,
    get_portfolio_repository,
)
from financial_assistant.news_graph.ingest import articles_of, ingest
from financial_assistant.news_graph.resolution import Resolver


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def book() -> dict[str, str]:
    return {p.ticker.upper(): p.name for p in get_portfolio_repository().load().positions}


def as_of_wall(value: date | None) -> datetime | None:
    if value is None:
        return None

    return datetime.combine(value, time_of_day.max, timezone.utc)


def checkpoint_path() -> Path:
    return get_settings().data_dir / "state" / "tgn" / "model.pt"


# -------------------------------------------------
# ingest
# -------------------------------------------------


def cmd_ingest(args) -> None:
    registry = get_model_registry()
    spec = registry.get(args.model)

    if not spec.is_local and not args.allow_hosted:
        sys.exit(
            f"{spec.id} is a hosted endpoint: one article takes minutes there. "
            "Run this on the GPU box (LLM_PROFILE=local), or pass --allow-hosted."
        )

    provider = registry.provider(args.model)
    names = book()
    tickers = [t.upper() for t in args.tickers] if args.tickers else list(names)
    archive = get_news_archive()

    items = articles_of(archive.read, tickers, start=None, end=as_of_wall(args.as_of))

    # The live cache holds what the wire brought since the
    # archive was filled; the graph should not lag the desk.
    cache = get_news_repository()
    for ticker in tickers:
        items.extend(cache.get(ticker, names.get(ticker, ""), end=as_of_wall(args.as_of)))

    log(f"{len(items)} articles on {len(tickers)} tickers; reading with {spec.id} ({args.workers} at a time)")

    result = ingest(
        items,
        store=get_news_graph_store(),
        provider=provider,
        resolver=Resolver(names),
        workers=args.workers,
        limit=args.limit,
        on_progress=log,
    )

    log(json.dumps(result))
    log(json.dumps(get_news_graph_store().counts()))


# -------------------------------------------------
# train / score
# -------------------------------------------------


def cmd_train(args) -> None:
    from financial_assistant.tgn.dataset import load_stream
    from financial_assistant.tgn.model import Hyperparameters, pick_device
    from financial_assistant.tgn.train import train

    store = get_news_graph_store()
    stream = load_stream(store, end=as_of_wall(args.as_of))
    device = pick_device(args.device)

    log(f"{stream.data.num_events} events, {stream.num_nodes} nodes, on {device}")

    hp = Hyperparameters(epochs=args.epochs, batch_size=args.batch_size, learning_rate=args.learning_rate)
    _, report = train(stream, hp=hp, device=device, checkpoint=checkpoint_path(), log=log)

    log(json.dumps(report.__dict__))


def cmd_score(args) -> None:
    import torch

    from financial_assistant.tgn.dataset import load_stream
    from financial_assistant.tgn.model import Hyperparameters, TemporalGraphNetwork, pick_device
    from financial_assistant.tgn.score import score

    store = get_news_graph_store()
    stream = load_stream(store, end=as_of_wall(args.as_of))
    device = pick_device(args.device)

    saved = torch.load(checkpoint_path(), map_location=device, weights_only=False)

    if saved["node_ids"] != stream.node_ids[: len(saved["node_ids"])]:
        sys.exit("The graph's nodes changed under the checkpoint: train again.")

    # Nodes that appeared after training get fresh memory rows:
    # the model treats them as new, which they are.
    model = TemporalGraphNetwork(stream.num_nodes, stream.data.msg.size(-1), Hyperparameters(**saved["hp"]), device)
    _load_grown(model, saved, stream.num_nodes)

    log(f"scoring {stream.data.num_events} events on {device}")
    scores = score(model, stream)

    name = f"tgn:{saved['report']['best_epoch']}"
    store.write_edge_scores(scores.edge_probs, name)
    store.write_signals(scores.daily, name)
    store.write_predictions(scores.predictions, name)

    log(f"{len(scores.edge_probs)} edges, {len(scores.daily)} security-days, {len(scores.predictions)} predicted edges")


def _load_grown(model, saved: dict, num_nodes: int) -> None:
    """Load weights; memory buffers sized to today's node count."""

    memory_state = saved["memory"]
    own = model.memory.state_dict()

    for key, value in memory_state.items():
        if value.shape == own[key].shape:
            own[key] = value
        # A buffer sized to the old node count (memory,
        # last_update): keep the fresh zeros, they are reset
        # before scoring anyway.

    model.memory.load_state_dict(own)
    model.gnn.load_state_dict(saved["gnn"])
    model.link_pred.load_state_dict(saved["link_pred"])


# -------------------------------------------------
# evaluate
# -------------------------------------------------


def cmd_evaluate(args) -> None:
    """
    Lift: how often a price shock follows a surprising news
    day, against how often it follows any day. A shock is an
    absolute daily log return beyond 2 standard deviations of
    the trailing 60 sessions. Historical frequencies, not a
    forecast, with the sample sizes shown.
    """

    import numpy as np
    import pandas as pd

    store = get_news_graph_store()
    signals = pd.DataFrame(store.signals())

    if signals.empty:
        sys.exit("No signals: run score first.")

    prices = get_market_repository().get_prices(tuple(signals["ticker"].unique()))
    prices["date"] = pd.to_datetime(prices["date"])
    wide = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    returns = np.log(wide).diff()
    z = returns / returns.rolling(60).std().shift(1)
    shock = (z.abs() > 2)

    horizon = args.horizon
    rows = []

    for ticker, group in signals.groupby("ticker"):
        if ticker not in shock.columns:
            continue

        s = shock[ticker]
        followed = {}

        for day in group["day"]:
            when = pd.Timestamp(day)
            after = s.loc[when + pd.Timedelta(days=1): when + pd.Timedelta(days=horizon * 2)].head(horizon)
            followed[day] = bool(after.any()) if len(after) else None

        group = group.assign(followed=group["day"].map(followed)).dropna(subset=["followed"])

        if len(group) < 20:
            continue

        top = group[group["surprise_mean"] >= group["surprise_mean"].quantile(0.9)]
        base = group["followed"].astype(float).mean()
        hit = top["followed"].astype(float).mean()

        rows.append((ticker, len(group), len(top), base, hit, hit / base if base else float("nan")))

    print(f"\n{'ticker':8} {'days':>5} {'top10%':>6} {'P(shock|any day)':>18} {'P(shock|surprising)':>20} {'lift':>6}")

    for ticker, n, k, base, hit, lift in rows:
        print(f"{ticker:8} {n:5d} {k:6d} {base:18.2f} {hit:20.2f} {lift:6.2f}")

    if rows:
        lifts = [r[5] for r in rows if np.isfinite(r[5])]
        print(f"\nmedian lift {np.median(lifts):.2f} over {len(rows)} securities, horizon {horizon} sessions")


# -------------------------------------------------
# watch
# -------------------------------------------------


def cmd_watch(args) -> None:
    """Refresh the wire for the book, read what is new, score, sleep."""

    names = book()
    cache = get_news_repository()

    while True:
        started = time.perf_counter()

        for ticker, company in names.items():
            try:
                cache.get(ticker, company, force=True)
            except Exception as error:
                log(f"{ticker}: refresh failed: {error}")

        cmd_ingest(argparse.Namespace(model=args.model, allow_hosted=args.allow_hosted, tickers=None,
                                      as_of=None, workers=args.workers, limit=None))

        if checkpoint_path().is_file():
            cmd_score(argparse.Namespace(as_of=None, device=args.device))

        log(f"cycle done in {time.perf_counter() - started:.0f}s; next in {args.every} min")
        time.sleep(args.every * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def common(sub, *, model=False, device=False):
        sub.add_argument("--as-of", type=date.fromisoformat, default=None, help="nothing after this date")
        if model:
            sub.add_argument("--model", default=None, help="registry id of the reader (default: LLM_PROFILE's)")
            sub.add_argument("--workers", type=int, default=get_settings().llm_workers)
            sub.add_argument("--allow-hosted", action="store_true")
        if device:
            sub.add_argument("--device", default="auto", help="auto | cpu | cuda | cuda:1")

    sub = commands.add_parser("ingest"); common(sub, model=True)
    sub.add_argument("--tickers", nargs="*")
    sub.add_argument("--limit", type=int, default=None, help="read at most this many new articles")
    sub.set_defaults(run=cmd_ingest)

    sub = commands.add_parser("train"); common(sub, device=True)
    sub.add_argument("--epochs", type=int, default=30)
    sub.add_argument("--batch-size", type=int, default=200)
    sub.add_argument("--learning-rate", type=float, default=1e-4)
    sub.set_defaults(run=cmd_train)

    sub = commands.add_parser("score"); common(sub, device=True)
    sub.set_defaults(run=cmd_score)

    sub = commands.add_parser("evaluate")
    sub.add_argument("--horizon", type=int, default=5, help="sessions after a signal day")
    sub.set_defaults(run=cmd_evaluate)

    sub = commands.add_parser("watch"); common(sub, model=True, device=True)
    sub.add_argument("--every", type=int, default=15, help="minutes between cycles")
    sub.set_defaults(run=cmd_watch)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
