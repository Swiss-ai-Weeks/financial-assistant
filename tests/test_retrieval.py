from datetime import (
    datetime,
    timezone,
)

from financial_assistant.domain import (
    SourceDocument,
)

from financial_assistant.research import (
    ResearchPlan,
    ResearchSourceClass,
    ResearchTask,
    ResearchTaskKind,
)

from financial_assistant.retrieval import (
    RetrievalStatus,
    SearchHit,
    execute_research_plan,
)


AS_OF = datetime(
    2026,
    9,
    16,
    12,
    0,
    tzinfo=timezone.utc,
)

RETRIEVED_AT = datetime(
    2026,
    9,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def make_plan() -> ResearchPlan:
    first = ResearchTask(
        task_id="TASK-AAA",
        kind=ResearchTaskKind.RECENT_NEWS,
        entities=("AAA",),
        question="What happened to AAA?",
        rationale="Investigate AAA.",
        source_preferences=(
            ResearchSourceClass.NEWS,
        ),
        lookback_days=7,
        priority=1,
    )

    second = ResearchTask(
        task_id="TASK-BBB",
        kind=ResearchTaskKind.RECENT_NEWS,
        entities=("BBB",),
        question="What happened to BBB?",
        rationale="Investigate BBB.",
        source_preferences=(
            ResearchSourceClass.NEWS,
        ),
        lookback_days=7,
        priority=1,
    )

    return ResearchPlan(
        plan_id="PLAN-1",
        anomaly_id="ANOMALY-1",
        as_of=AS_OF,
        tasks=(
            first,
            second,
        ),
    )


class FakeSearchProvider:
    name = "fake-search"

    def search(
        self,
        query: str,
        *,
        task_id: str,
        limit: int = 5,
        as_of=None,
    ):
        # Same historical document appears for both
        # tasks, allowing us to test URL reuse.
        historical = SearchHit(
            hit_id=f"HIT-{task_id}-1",
            task_id=task_id,
            provider=self.name,
            query=query,
            rank=1,
            title="Historical article",
            url=(
                "https://example.com/"
                "shared-article"
            ),
            snippet="Relevant historical news.",
            publisher="Example News",
            published_at=datetime(
                2026,
                9,
                15,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        # This result contains look-ahead information
        # and must not enter the evidence corpus.
        future = SearchHit(
            hit_id=f"HIT-{task_id}-2",
            task_id=task_id,
            provider=self.name,
            query=query,
            rank=2,
            title="Future article",
            url=(
                "https://example.com/"
                f"future-{task_id}"
            ),
            snippet="Published after cutoff.",
            publisher="Example News",
            published_at=datetime(
                2026,
                9,
                17,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        return (
            historical,
            future,
        )[:limit]


class FakeDocumentFetcher:
    name = "fake-fetcher"

    def __init__(self):
        self.fetch_count = 0

    def fetch(
        self,
        hit: SearchHit,
        *,
        retrieved_at: datetime,
    ) -> SourceDocument:
        self.fetch_count += 1

        return SourceDocument(
            document_id="DOC-SHARED",
            title=hit.title,
            publisher=(
                hit.publisher
                or "Unknown publisher"
            ),
            url=hit.url,
            published_at=(
                hit.published_at
                or retrieved_at
            ),
            retrieved_at=retrieved_at,
            text=(
                "Normalized article body "
                "for testing."
            ),
            lineage_id="LINEAGE-SHARED",
        )


def test_retrieval_filters_known_future_information():
    fetcher = FakeDocumentFetcher()

    bundle = execute_research_plan(
        make_plan(),
        search_provider=FakeSearchProvider(),
        document_fetcher=fetcher,
        retrieved_at=RETRIEVED_AT,
    )

    statuses = [
        record.status
        for record in bundle.records
    ]

    assert (
        RetrievalStatus.FILTERED_FUTURE
        in statuses
    )

    # No future document entered the normalized
    # document corpus.
    assert len(bundle.documents) == 1

    assert (
        bundle.documents[0].published_at
        <= AS_OF
    )


def test_same_url_is_fetched_only_once():
    fetcher = FakeDocumentFetcher()

    bundle = execute_research_plan(
        make_plan(),
        search_provider=FakeSearchProvider(),
        document_fetcher=fetcher,
        retrieved_at=RETRIEVED_AT,
    )

    assert fetcher.fetch_count == 1

    statuses = [
        record.status
        for record in bundle.records
    ]

    assert RetrievalStatus.FETCHED in statuses
    assert RetrievalStatus.REUSED in statuses


def test_retrieval_keeps_execution_provenance():
    fetcher = FakeDocumentFetcher()

    bundle = execute_research_plan(
        make_plan(),
        search_provider=FakeSearchProvider(),
        document_fetcher=fetcher,
        retrieved_at=RETRIEVED_AT,
    )

    assert len(bundle.hits) == 4
    assert len(bundle.records) == 4

    for record in bundle.records:
        assert record.task_id
        assert record.hit_id
        assert record.query
        assert record.provider == "fake-search"
