"""
The news graph: what one reading contributes, what the store
keeps, and what the WIRE page reads back as of a date.
"""

from datetime import date, datetime, timedelta, timezone

from financial_assistant.api.clock import DeskClock
from financial_assistant.api.models import NewsItem
from financial_assistant.api.services.wire_service import WireService
from financial_assistant.news_graph import NewsGraphStore, NodeKind
from financial_assistant.news_graph.extraction import to_graph
from financial_assistant.news_graph.ingest import ingest, one_per_story
from financial_assistant.news_graph.models import Direction, EventType, Extraction
from financial_assistant.news_graph.resolution import Resolver, normalise

BOOK = {"ORCL": "Oracle Corp", "MU": "Micron Technology Inc", "AMAT": "Applied Materials"}

T0 = datetime(2026, 5, 5, 14, 0, tzinfo=timezone.utc)


def item(news_id, ticker, title, when=T0, summary="") -> NewsItem:
    return NewsItem(
        news_id=news_id,
        ticker=ticker,
        title=title,
        url=f"https://example.com/{news_id}",
        publisher="Wire",
        published_at=when,
        summary=summary,
        provider="finnhub",
    )


class ScriptedReader:
    provider_name = "fake"
    model_name = "scripted"

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls = 0

    def complete_json(self, *, system, user, reasoning=False):
        self.calls += 1
        title = user.split("Title: ", 1)[1].splitlines()[0]

        return self.answers[title]


def test_names_resolve_conservatively():
    resolver = Resolver(BOOK)

    assert normalise("Micron Technology, Inc.") == "micron"
    assert resolver.security("Micron Technology Inc") == "MU"
    assert resolver.security("micron technology") == "MU"
    assert resolver.security("Applied Materials Inc.") == "AMAT"
    # "Technology" is a suffix, so "Micron" is Micron; a bare
    # "Applied" is not Applied Materials.
    assert resolver.security("Micron") == "MU"
    assert resolver.security("Applied") is None
    assert resolver.security("OpenAI") is None


def test_a_reading_becomes_edges_from_the_security_to_what_it_names():
    resolver = Resolver(BOOK)
    extraction = Extraction(
        event_type=EventType.CUSTOMER,
        event="Oracle OpenAI cloud contract",
        entities=({"name": "OpenAI", "kind": "company"}, {"name": "Micron Technology Inc", "kind": "company"}),
        direction=Direction.POSITIVE,
        materiality="high",
    )

    nodes, edges = to_graph(item("n1", "ORCL", "Oracle signs OpenAI"), extraction, resolver)

    kinds = {n.kind for n in nodes}
    assert kinds == {NodeKind.SECURITY, NodeKind.ARTICLE, NodeKind.EVENT_TYPE, NodeKind.EVENT, NodeKind.ENTITY}

    targets = {(e.kind, e.dst) for e in edges}
    assert ("reports_type", "event_type:customer") in targets
    assert ("reports", "event:customer:oracle openai cloud contract:2026-05-04") in targets
    assert ("mentions", "entity:company:openai") in targets
    # Another holding named in the article is linked as a security, not an entity.
    assert ("mentions", "security:MU") in targets
    assert all(e.src == "security:ORCL" and e.t == T0 and e.article_id == "n1" for e in edges)
    assert all(e.props["event_type"] == "customer" and e.props["direction"] == "positive" for e in edges)


def test_the_same_article_is_read_once_per_holding_and_replaced_not_duplicated(tmp_path):
    store = NewsGraphStore(tmp_path / "g.sqlite")
    resolver = Resolver(BOOK)
    reader = ScriptedReader(
        {
            "Micron and Oracle in a deal": {
                "event_type": "customer", "event": "Micron Oracle memory deal",
                "entities": [{"name": "Oracle Corp", "kind": "company"}], "direction": "positive", "materiality": "medium",
            },
        }
    )

    # Finnhub tags one story to both tickers: same news_id, two tickers.
    items = [item("n7", "MU", "Micron and Oracle in a deal"), item("n7", "ORCL", "Micron and Oracle in a deal")]

    first = ingest(items, store=store, provider=reader, resolver=resolver, workers=1)
    again = ingest(items, store=store, provider=reader, resolver=resolver, workers=1)

    assert first["read"] == 2 and again["candidates"] == 0
    assert reader.calls == 2

    edges = store.edges()
    assert {e["src"] for e in edges} == {"security:MU", "security:ORCL"}
    assert store.counts()["articles"] == 1 and store.counts()["readings"] == 2

    # The syndicated copy (another URL, same headline, same day) is not read again.
    copy = item("n8", "MU", "Micron and Oracle in a deal", when=T0 + timedelta(hours=3))
    assert one_per_story(items + [copy]) == items


def test_a_failed_reading_is_recorded_and_not_retried(tmp_path):
    store = NewsGraphStore(tmp_path / "g.sqlite")

    class Broken:
        provider_name = "fake"; model_name = "broken"
        def complete_json(self, **_):
            raise RuntimeError("gateway down")

    result = ingest([item("n1", "ORCL", "x")], store=store, provider=Broken(), resolver=Resolver(BOOK), workers=1)
    assert result["failed"] == 1
    assert store.counts()["failed"] == 1
    assert ingest([item("n1", "ORCL", "x")], store=store, provider=Broken(), resolver=Resolver(BOOK), workers=1)["candidates"] == 0

    assert store.retry_failed() == 1
    assert ingest([item("n1", "ORCL", "x")], store=store, provider=Broken(), resolver=Resolver(BOOK), workers=1)["candidates"] == 1


def test_the_wire_reads_the_graph_as_of_the_desk_date(tmp_path):
    store = NewsGraphStore(tmp_path / "g.sqlite")
    resolver = Resolver(BOOK)
    answers = {
        "Oracle wins OpenAI": {"event_type": "customer", "event": "Oracle OpenAI contract", "entities": [{"name": "OpenAI", "kind": "company"}], "direction": "positive", "materiality": "high"},
        "Oracle sued": {"event_type": "litigation", "event": "Oracle shareholder lawsuit", "entities": [], "direction": "negative", "materiality": "medium"},
        "Five stocks to watch": {"event_type": "market_commentary", "event": None, "entities": [], "direction": "neutral", "materiality": "low"},
    }
    items = [
        item("a", "ORCL", "Oracle wins OpenAI", when=T0),
        item("b", "ORCL", "Oracle sued", when=T0 + timedelta(days=10)),
        item("c", "ORCL", "Five stocks to watch", when=T0 + timedelta(days=10)),
    ]
    ingest(items, store=store, provider=ScriptedReader(answers), resolver=resolver, workers=1)
    store.write_edge_scores([(e["edge_id"], 0.1) for e in store.edges(kinds=["reports"]) if e["article_id"] == "b"], "t")

    clock = DeskClock(None)
    wire = WireService(store, clock, checkpoint_exists=lambda: False)

    feed = wire.feed(["ORCL"], days=400)
    assert [r["label"] for r in feed] == ["Oracle shareholder lawsuit", "Oracle OpenAI contract"]
    assert feed[0]["surprise"] == 0.9 and feed[0]["direction"] == "negative"
    assert feed[0]["articles"][0]["title"] == "Oracle sued"
    assert "Five stocks to watch" not in str(feed)

    graph = wire.graph("ORCL", days=400)
    assert {n["id"] for n in graph["nodes"]} >= {"security:ORCL", "entity:company:openai", "event_type:litigation"}
    assert all(e["src"] == "security:ORCL" for e in graph["edges"])

    # Replayed to the day of the first article: the lawsuit does not exist yet.
    clock.set(date(2026, 5, 6))
    assert [r["label"] for r in wire.feed(["ORCL"], days=400)] == ["Oracle OpenAI contract"]
    assert all(e["t"] <= "2026-05-06T23:59:59.999999+00:00" for e in wire.graph("ORCL", days=400)["edges"])
