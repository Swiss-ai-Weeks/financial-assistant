from datetime import datetime, timezone

from financial_assistant.domain import SourceDocument
from financial_assistant.retrieval.composite import (
    CompositeSearchProvider,
    DispatchingDocumentFetcher,
)
from financial_assistant.retrieval.models import SearchHit


class FakeSearchProvider:
    def __init__(self, name: str):
        self.name = name

    def search(
        self,
        query: str,
        *,
        task_id: str,
        limit: int = 5,
        as_of=None,
    ):
        return (
            SearchHit(
                hit_id=f"{task_id}:{self.name}:1",
                task_id=task_id,
                provider=self.name,
                query=query,
                rank=1,
                title=f"{self.name} result",
                url=f"https://example.com/{self.name}/1",
                snippet="example",
            ),
        )


class FakeFetcher:
    def __init__(self, name: str):
        self.name = name
        self.calls = 0

    def fetch(
        self,
        hit: SearchHit,
        *,
        retrieved_at: datetime,
    ):
        self.calls += 1

        return SourceDocument(
            document_id=f"DOC-{self.name}",
            title=hit.title,
            publisher=self.name,
            url=hit.url,
            published_at=None,
            published_date_only=False,
            retrieved_at=retrieved_at,
            text=f"document from {self.name}",
        )


def test_composite_search_keeps_both_providers():
    provider = CompositeSearchProvider(
        providers=(
            FakeSearchProvider("bookreader"),
            FakeSearchProvider("searxng"),
        )
    )

    hits = provider.search(
        "Federal Reserve",
        task_id="TASK-1",
        limit=2,
        as_of=datetime(
            2026,
            9,
            17,
            tzinfo=timezone.utc,
        ),
    )

    assert len(hits) == 2
    assert hits[0].provider == "bookreader"
    assert hits[1].provider == "searxng"


def test_dispatching_fetcher_uses_matching_fetcher():
    bookreader_fetcher = FakeFetcher("bookreader")
    searxng_fetcher = FakeFetcher("searxng")

    dispatcher = DispatchingDocumentFetcher(
        fetchers={
            "bookreader": bookreader_fetcher,
            "searxng": searxng_fetcher,
        }
    )

    retrieved_at = datetime(
        2026,
        9,
        19,
        tzinfo=timezone.utc,
    )

    bookreader_hit = SearchHit(
        hit_id="TASK-1:bookreader:1",
        task_id="TASK-1",
        provider="bookreader",
        query="test",
        rank=1,
        title="BookReader result",
        url="https://example.com/bookreader",
    )

    searxng_hit = SearchHit(
        hit_id="TASK-1:searxng:1",
        task_id="TASK-1",
        provider="searxng",
        query="test",
        rank=2,
        title="SearXNG result",
        url="https://example.com/searxng",
    )

    dispatcher.fetch(
        bookreader_hit,
        retrieved_at=retrieved_at,
    )

    dispatcher.fetch(
        searxng_hit,
        retrieved_at=retrieved_at,
    )

    assert bookreader_fetcher.calls == 1
    assert searxng_fetcher.calls == 1
