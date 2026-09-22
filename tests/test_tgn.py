"""
The temporal graph network learns a synthetic stream and finds
the one day that breaks its pattern.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

pytest.importorskip("torch_geometric")

from financial_assistant.news_graph import NewsGraphStore  # noqa: E402
from financial_assistant.news_graph.models import Edge, Node, NodeKind  # noqa: E402
from financial_assistant.tgn.dataset import load_stream, message_dim  # noqa: E402
from financial_assistant.tgn.model import Hyperparameters  # noqa: E402
from financial_assistant.tgn.score import score  # noqa: E402
from financial_assistant.tgn.train import train  # noqa: E402


def synthetic(store: NewsGraphStore, *, days: int = 300, break_day: int = 250) -> None:
    """Two securities, each with its own partners; on one day AAA meets a regulator."""

    rng = np.random.default_rng(0)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    partners = {"AAA": [f"entity:company:p{i}" for i in range(5)], "BBB": [f"entity:company:q{i}" for i in range(5)]}
    n = 0

    for day in range(days):
        for ticker, peers in partners.items():
            for hour in range(4):
                n += 1
                when = t0 + timedelta(days=day, hours=hour)
                dst = "entity:regulator:doj" if (day == break_day and ticker == "AAA") else rng.choice(peers)
                props = {"event_type": "market_commentary", "direction": "neutral", "materiality": "low"}
                security = f"security:{ticker}"

                store.record(
                    article_id=f"a{n}", ticker=ticker, published_at=when, model="fake", prompt="v", payload={}, error=None,
                    nodes=[Node(security, NodeKind.SECURITY, ticker), Node(dst, NodeKind.ENTITY, dst)],
                    edges=[Edge(security, dst, "mentions", when, f"a{n}", props)],
                )


def test_the_stream_is_the_store_in_time_order(tmp_path):
    store = NewsGraphStore(tmp_path / "g.sqlite")
    synthetic(store, days=5)

    stream = load_stream(store)

    assert stream.data.num_events == 40
    assert stream.data.msg.shape == (40, message_dim())
    assert bool((stream.data.t[1:] >= stream.data.t[:-1]).all())
    assert set(stream.securities()) == {"AAA", "BBB"}


def test_the_model_learns_the_pattern_and_flags_the_day_that_breaks_it(tmp_path):
    store = NewsGraphStore(tmp_path / "g.sqlite")
    synthetic(store)
    stream = load_stream(store)

    model, report = train(stream, hp=Hyperparameters(epochs=25, batch_size=100, learning_rate=1e-3), log=lambda _: None)

    assert report.test_auc > 0.6

    scores = score(model, stream)
    daily = {(ticker, day): row for ticker, day, *row in scores.daily}

    break_day = (datetime(2025, 1, 1) + timedelta(days=250)).date().isoformat()
    on_break = daily[("AAA", break_day)][1]  # the day's largest surprise
    typical = np.median([row[1] for (ticker, day), row in daily.items() if ticker == "AAA" and day != break_day])

    assert on_break > typical + 0.15

    # Every edge scored, every security-day has a drift after the first.
    assert len(scores.edge_probs) == stream.data.num_events
    assert sum(row[2] is not None for row in daily.values()) >= len(daily) - 2
    assert {p[0] for p in scores.predictions} == {"AAA", "BBB"}
