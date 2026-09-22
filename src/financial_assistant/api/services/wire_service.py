"""
The WIRE page: the news graph of the book, as of the desk's
date. Everything here is a read of the store; nothing is
fetched or computed from prices.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from financial_assistant.api.clock import DeskClock
from financial_assistant.news_graph import NewsGraphStore, NodeKind

# What "recent" means for the graph and feed views.
DEFAULT_DAYS = 30


class WireService:
    def __init__(self, store: NewsGraphStore, clock: DeskClock, checkpoint_exists):
        self._store = store
        self._clock = clock
        self._checkpoint_exists = checkpoint_exists

    def _wall(self) -> datetime:
        as_of = self._clock.as_of

        if as_of is None:
            return datetime.now(timezone.utc)

        return datetime.combine(as_of, time.max, timezone.utc)

    def status(self) -> dict:
        counts = self._store.counts()

        return {
            **counts,
            "as_of": self._clock.as_of.isoformat() if self._clock.as_of else None,
            "model_trained": bool(self._checkpoint_exists()),
        }

    def signals(self, ticker: str) -> list[dict]:
        return self._store.signals(ticker, end=self._wall())

    def graph(self, ticker: str, *, days: int = DEFAULT_DAYS) -> dict:
        """
        The security's neighbourhood over the last `days`
        before the desk's date: nodes, the edges with the
        probability the model gave each, and the edges the
        model expects next (dashed, in the view).
        """

        end = self._wall()
        start = end - timedelta(days=days)
        security = f"security:{ticker.upper()}"

        edges = self._store.edges(start=start, end=end, touching=[security])
        probs = self._store.edge_scores(e["edge_id"] for e in edges)

        node_ids = {security} | {e["src"] for e in edges} | {e["dst"] for e in edges}
        nodes = self._store.nodes(node_ids)

        # Article provenance for every edge, so a click resolves
        # to a headline.
        articles = self._store.nodes(f"article:{e['article_id']}" for e in edges)

        as_of_day = self._store.latest_prediction_date(ticker)
        predictions = self._store.predictions(ticker, as_of=as_of_day) if as_of_day else []
        prediction_nodes = self._store.nodes(p["node_id"] for p in predictions)

        def node_row(node):
            return {"id": node.node_id, "kind": node.kind.value, "label": node.label, **node.props}

        return {
            "ticker": ticker.upper(),
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "nodes": [node_row(n) for n in {**nodes, **prediction_nodes}.values() if n.kind != NodeKind.ARTICLE],
            "edges": [
                {
                    "id": e["edge_id"],
                    "src": e["src"],
                    "dst": e["dst"],
                    "kind": e["kind"],
                    "t": e["t"].isoformat(),
                    "prob": probs.get(e["edge_id"]),
                    "event_type": e["props"].get("event_type"),
                    "direction": e["props"].get("direction"),
                    "materiality": e["props"].get("materiality"),
                    "article": _article(articles.get(f"article:{e['article_id']}")),
                }
                for e in edges
            ],
            "predictions": [
                {"dst": p["node_id"], "prob": p["prob"], "as_of": as_of_day}
                for p in predictions
                if p["node_id"] != security
            ],
        }

    def feed(self, tickers: list[str], *, days: int = DEFAULT_DAYS, limit: int = 300) -> list[dict]:
        """
        What happened to the book, one row per canonical event
        rather than per article, newest first, at most `limit`
        rows. Market commentary (recaps, lists, opinion) is left
        out: it is coverage, not an event.
        """

        end = self._wall()
        start = end - timedelta(days=days)
        securities = [f"security:{t.upper()}" for t in tickers]

        edges = self._store.edges(start=start, end=end, touching=securities, kinds=["reports"])
        probs = self._store.edge_scores(e["edge_id"] for e in edges)
        events = self._store.nodes(e["dst"] for e in edges)
        articles = self._store.nodes(f"article:{e['article_id']}" for e in edges)

        grouped: dict[str, dict] = {}

        for e in edges:
            row = grouped.setdefault(
                e["dst"],
                {
                    "event": e["dst"],
                    "label": events[e["dst"]].label if e["dst"] in events else e["dst"],
                    "event_type": e["props"].get("event_type"),
                    "tickers": [],
                    "first": e["t"].isoformat(),
                    "last": e["t"].isoformat(),
                    "articles": [],
                    "direction": defaultdict(int),
                    "materiality": e["props"].get("materiality"),
                    "surprise": None,
                },
            )

            ticker = e["src"].split(":", 1)[1]

            if ticker not in row["tickers"]:
                row["tickers"].append(ticker)

            row["last"] = max(row["last"], e["t"].isoformat())
            row["direction"][e["props"].get("direction", "neutral")] += 1

            if (article := _article(articles.get(f"article:{e['article_id']}"))) and article not in row["articles"]:
                row["articles"].append({**article, "ticker": ticker})

            if (prob := probs.get(e["edge_id"])) is not None:
                surprise = 1 - prob
                row["surprise"] = max(row["surprise"] or 0, surprise)

        rows = []

        for row in grouped.values():
            direction = max(row["direction"], key=row["direction"].get)
            rows.append({**row, "direction": direction, "count": len(row["articles"])})

        rows = [r for r in rows if r["event_type"] not in ("market_commentary", "other")]
        rows.sort(key=lambda r: (r["last"], r["count"]), reverse=True)

        return rows[:limit]


def _article(node) -> dict | None:
    if node is None:
        return None

    return {
        "title": node.label,
        "url": node.props.get("url"),
        "publisher": node.props.get("publisher"),
        "published_at": node.props.get("published_at"),
    }
