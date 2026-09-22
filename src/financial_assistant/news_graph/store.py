"""
The graph on disk: SQLite, one file.

An edge list with timestamps IS the graph. What the desk
needs most is time ("everything published before D", "the
events of ORCL in the two weeks before the break"), which is
an indexed range scan here, and the temporal graph network
wants exactly this table, sorted by t. Community detection
and neighbourhood walks run in memory on the as-of subgraph,
which is small.

Every write is idempotent: an article is extracted once
(`extractions`), and its edges are replaced as a unit.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .models import Edge, Node, NodeKind

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id     TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    label       TEXT NOT NULL,
    props       TEXT NOT NULL DEFAULT '{}',
    first_seen  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nodes_kind ON nodes (kind);

CREATE TABLE IF NOT EXISTS edges (
    edge_id     INTEGER PRIMARY KEY,
    src         TEXT NOT NULL,
    dst         TEXT NOT NULL,
    kind        TEXT NOT NULL,
    t           TEXT NOT NULL,
    article_id  TEXT NOT NULL,
    props       TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS edges_t ON edges (t);
CREATE INDEX IF NOT EXISTS edges_src_t ON edges (src, t);
CREATE INDEX IF NOT EXISTS edges_dst_t ON edges (dst, t);
CREATE INDEX IF NOT EXISTS edges_article ON edges (article_id);

CREATE TABLE IF NOT EXISTS extractions (
    article_id    TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    model         TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    extracted_at  TEXT NOT NULL,
    payload       TEXT NOT NULL,
    error         TEXT,
    PRIMARY KEY (article_id, ticker)
);
CREATE INDEX IF NOT EXISTS extractions_ticker ON extractions (ticker, published_at);

CREATE TABLE IF NOT EXISTS signals (
    ticker        TEXT NOT NULL,
    day           TEXT NOT NULL,
    model         TEXT NOT NULL,
    surprise_mean REAL,
    surprise_max  REAL,
    drift         REAL,
    edges         INTEGER NOT NULL,
    scored_at     TEXT NOT NULL,
    PRIMARY KEY (ticker, day, model)
);

CREATE TABLE IF NOT EXISTS edge_scores (
    edge_id   INTEGER PRIMARY KEY,
    model     TEXT NOT NULL,
    prob      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    ticker     TEXT NOT NULL,
    node_id    TEXT NOT NULL,
    as_of      TEXT NOT NULL,
    model      TEXT NOT NULL,
    prob       REAL NOT NULL,
    PRIMARY KEY (ticker, node_id, as_of, model)
);
"""


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat()


class NewsGraphStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()

        path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")

        return connection

    # -------------------------------------------------
    # Writing
    # -------------------------------------------------

    def record(
        self,
        *,
        article_id: str,
        ticker: str,
        published_at: datetime,
        model: str,
        prompt: str,
        payload: dict | None,
        error: str | None,
        nodes: Iterable[Node],
        edges: Iterable[Edge],
    ) -> None:
        """
        One article's reading for one security (an article
        tagged to two holdings is read once per holding): its
        extraction, the nodes it introduces and its edges,
        replacing any earlier reading of the same pair. A
        failed extraction is recorded too, so it is not retried
        on every pass; `retry_failed` forgets it.
        """

        now = _iso(datetime.now(timezone.utc))

        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO extractions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    article_id,
                    ticker,
                    _iso(published_at),
                    model,
                    prompt,
                    now,
                    json.dumps(payload or {}),
                    error,
                ),
            )

            connection.executemany(
                "INSERT OR IGNORE INTO nodes VALUES (?, ?, ?, ?, ?)",
                [
                    (node.node_id, node.kind.value, node.label, json.dumps(node.props), now)
                    for node in nodes
                ],
            )

            connection.execute(
                "DELETE FROM edges WHERE article_id = ? AND src = ?",
                (article_id, f"security:{ticker.upper()}"),
            )
            connection.executemany(
                "INSERT INTO edges (src, dst, kind, t, article_id, props) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (edge.src, edge.dst, edge.kind, _iso(edge.t), edge.article_id, json.dumps(edge.props))
                    for edge in edges
                ],
            )

    def retry_failed(self) -> int:
        with self._lock, self._connect() as connection:
            return connection.execute("DELETE FROM extractions WHERE error IS NOT NULL").rowcount

    def write_signals(self, rows: Iterable[tuple], model: str) -> None:
        """rows: (ticker, day, surprise_mean, surprise_max, drift, edges)."""

        now = _iso(datetime.now(timezone.utc))

        with self._lock, self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(t, d, model, sm, sx, dr, n, now) for t, d, sm, sx, dr, n in rows],
            )

    def write_edge_scores(self, rows: Iterable[tuple[int, float]], model: str) -> None:
        with self._lock, self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO edge_scores VALUES (?, ?, ?)",
                [(edge_id, model, prob) for edge_id, prob in rows],
            )

    def write_predictions(self, rows: Iterable[tuple], model: str) -> None:
        """rows: (ticker, node_id, as_of, prob)."""

        with self._lock, self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO predictions VALUES (?, ?, ?, ?, ?)",
                [(t, n, a, model, p) for t, n, a, p in rows],
            )

    # -------------------------------------------------
    # Reading
    # -------------------------------------------------

    def extracted(self) -> set[tuple[str, str]]:
        """(article_id, ticker) pairs already read."""

        with self._connect() as connection:
            return {(row[0], row[1]) for row in connection.execute("SELECT article_id, ticker FROM extractions")}

    def counts(self) -> dict:
        with self._connect() as connection:
            def one(sql: str, *params):
                return connection.execute(sql, params).fetchone()[0]

            return {
                "articles": one("SELECT COUNT(DISTINCT article_id) FROM extractions WHERE error IS NULL"),
                "readings": one("SELECT COUNT(*) FROM extractions WHERE error IS NULL"),
                "failed": one("SELECT COUNT(*) FROM extractions WHERE error IS NOT NULL"),
                "nodes": one("SELECT COUNT(*) FROM nodes"),
                "edges": one("SELECT COUNT(*) FROM edges"),
                "first": one("SELECT MIN(t) FROM edges"),
                "last": one("SELECT MAX(t) FROM edges"),
                "scored_edges": one("SELECT COUNT(*) FROM edge_scores"),
                "signal_days": one("SELECT COUNT(*) FROM signals"),
            }

    def nodes(self, node_ids: Iterable[str]) -> dict[str, Node]:
        ids = list(dict.fromkeys(node_ids))

        if not ids:
            return {}

        found: dict[str, Node] = {}

        with self._connect() as connection:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                marks = ",".join("?" * len(chunk))

                for row in connection.execute(
                    f"SELECT node_id, kind, label, props FROM nodes WHERE node_id IN ({marks})", chunk
                ):
                    found[row["node_id"]] = Node(
                        row["node_id"], NodeKind(row["kind"]), row["label"], json.loads(row["props"])
                    )

        return found

    def edges(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        touching: Iterable[str] | None = None,
        kinds: Iterable[str] | None = None,
    ) -> list[dict]:
        """
        Edges in publication order. `touching` keeps those with
        either end in the given ids; `end` is the as-of wall.
        """

        clauses, params = [], []

        if start is not None:
            clauses.append("t >= ?"); params.append(_iso(start))
        if end is not None:
            clauses.append("t <= ?"); params.append(_iso(end))
        if touching is not None:
            ids = list(touching)
            marks = ",".join("?" * len(ids))
            clauses.append(f"(src IN ({marks}) OR dst IN ({marks}))")
            params += ids + ids
        if kinds is not None:
            ks = list(kinds)
            clauses.append(f"kind IN ({','.join('?' * len(ks))})")
            params += ks

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._connect() as connection:
            return [
                {
                    "edge_id": row["edge_id"],
                    "src": row["src"],
                    "dst": row["dst"],
                    "kind": row["kind"],
                    "t": datetime.fromisoformat(row["t"]),
                    "article_id": row["article_id"],
                    "props": json.loads(row["props"]),
                }
                for row in connection.execute(
                    f"SELECT * FROM edges {where} ORDER BY t, edge_id", params
                )
            ]

    def extractions(self, article_ids: Iterable[str]) -> dict[str, dict]:
        ids = list(dict.fromkeys(article_ids))
        found: dict[str, dict] = {}

        with self._connect() as connection:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                marks = ",".join("?" * len(chunk))

                for row in connection.execute(
                    f"SELECT article_id, ticker, published_at, payload FROM extractions "
                    f"WHERE article_id IN ({marks}) AND error IS NULL",
                    chunk,
                ):
                    found[row["article_id"]] = {
                        "ticker": row["ticker"],
                        "published_at": row["published_at"],
                        **json.loads(row["payload"]),
                    }

        return found

    def signals(self, ticker: str | None = None, *, end: datetime | None = None) -> list[dict]:
        clauses, params = [], []

        if ticker is not None:
            clauses.append("ticker = ?"); params.append(ticker.upper())
        if end is not None:
            clauses.append("day <= ?"); params.append(end.date().isoformat())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM signals {where} ORDER BY ticker, day", params
                )
            ]

    def edge_scores(self, edge_ids: Iterable[str]) -> dict[int, float]:
        ids = list(edge_ids)
        found: dict[int, float] = {}

        with self._connect() as connection:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                marks = ",".join("?" * len(chunk))

                for row in connection.execute(
                    f"SELECT edge_id, prob FROM edge_scores WHERE edge_id IN ({marks})", chunk
                ):
                    found[row["edge_id"]] = row["prob"]

        return found

    def predictions(self, ticker: str, *, as_of: str) -> list[dict]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT node_id, prob FROM predictions WHERE ticker = ? AND as_of = ? "
                    "ORDER BY prob DESC",
                    (ticker.upper(), as_of),
                )
            ]

    def latest_prediction_date(self, ticker: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT MAX(as_of) FROM predictions WHERE ticker = ?", (ticker.upper(),)
            ).fetchone()

            return row[0]
