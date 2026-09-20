import json
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from financial_assistant.api.repositories import (
    ArchiveNewsSource,
    CachedDocumentFetcher,
    FinnhubDownloader,
    GdeltClient,
    GdeltDownloader,
    MarketDataRepository,
    NewsArchive,
    NewsRepository,
)
from financial_assistant.api.repositories.gdelt import (
    GdeltRateLimited,
    build_query,
)
from financial_assistant.domain import SourceDocument
from financial_assistant.retrieval import SearchHit


UTC = timezone.utc
RATE_LIMITED = "Please limit requests to one every 5 seconds or contact us."


class FakeGdelt:
    """
    Stands in for the GDELT API and for the wall clock.
    Sleeping advances the clock instead of waiting.
    """

    def __init__(self, responses=None):
        self.requests = []
        self.request_times = []
        self.responses = list(responses or [])
        self.now = 0.0

    def get(self, url):
        params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}

        self.requests.append(params)
        self.request_times.append(self.now)

        if self.responses:
            return self.responses.pop(0)

        # One article per slice, stamped inside the slice.
        start = params["startdatetime"]

        return json.dumps(
            {
                "articles": [
                    {
                        "url": f"https://news.example.com/{start}",
                        "title": "Bank of America  slips on bond losses",
                        "seendate": f"{start[:8]}T120000Z",
                        "domain": "news.example.com",
                        "sourcecountry": "United States",
                    }
                ]
            }
        )

    def sleep(self, seconds):
        self.now += seconds

    def client(self):
        return GdeltClient(
            http_get=self.get,
            sleep=self.sleep,
            clock=lambda: self.now,
        )

    def downloader(self):
        return GdeltDownloader(self.client())


def test_query_uses_the_written_company_name():
    assert build_query("BAC", "Bank of America Corporation").startswith(
        '"Bank of America" ('
    )

    assert build_query("NVDA", "NVIDIA Corporation").startswith("NVIDIA (")
    assert "sourcelang:english" in build_query("XYZ", "XYZ")
    assert "-domain:tickerreport.com" in build_query("XYZ", "XYZ")


def test_content_farms_never_reach_the_archive(tmp_path):
    farm = json.dumps(
        {
            "articles": [
                {"url": "https://cnbc.com/a", "title": "Real", "seendate": "20260203T120000Z", "domain": "cnbc.com"},
                {"url": "https://tickerreport.com/b", "title": "Templated", "seendate": "20260203T120000Z", "domain": "tickerreport.com"},
            ]
        }
    )

    gdelt = FakeGdelt(responses=[farm])
    archive = NewsArchive(tmp_path)

    archive.download(
        gdelt.downloader(),
        "BAC",
        "Bank of America Corporation",
        start=datetime(2026, 2, 2, tzinfo=UTC),
        end=datetime(2026, 2, 3, tzinfo=UTC),
        now=datetime(2026, 9, 19, tzinfo=UTC),
    )

    assert [item.title for item in archive.read("BAC")] == ["Real"]


def test_providers_share_one_archive_and_one_copy_of_a_story(tmp_path):
    """
    The same URL reported by two providers is one article,
    and each provider resumes independently of the other.
    """

    calls = []

    def finnhub_api(url):
        calls.append(url)

        return json.dumps(
            [
                {
                    "headline": "Bank of America slips on bond losses",
                    "url": "https://news.example.com/20260201000000",
                    "datetime": 1769947200,
                    "source": "Example Wire",
                    "summary": "Unrealised losses widened.",
                },
                {
                    "headline": "Only Finnhub has this one",
                    "url": "https://news.example.com/finnhub-only",
                    "datetime": 1769950800,
                    "source": "Example Wire",
                    "summary": "",
                },
            ]
        )

    finnhub = FinnhubDownloader("key", http_get=finnhub_api, sleep=lambda s: None)
    gdelt = FakeGdelt()
    archive = NewsArchive(tmp_path)

    window = {
        "start": datetime(2026, 2, 1, tzinfo=UTC),
        "end": datetime(2026, 2, 7, tzinfo=UTC),
        "now": datetime(2026, 9, 19, tzinfo=UTC),
    }

    assert archive.download(finnhub, "BAC", "Bank of America", **window) == 2
    assert archive.download(gdelt.downloader(), "BAC", "Bank of America", **window) == 0
    assert archive.download(finnhub, "BAC", "Bank of America", **window) == 0

    assert len(calls) == 1
    assert "symbol=BAC" in calls[0] and "from=2026-02-01" in calls[0]

    items = {item.title: item for item in archive.read("BAC")}

    assert set(items) == {
        "Bank of America slips on bond losses",
        "Only Finnhub has this one",
    }

    # First provider to report a story keeps it, summary included.
    story = items["Bank of America slips on bond losses"]

    assert story.provider == "finnhub"
    assert story.summary == "Unrealised losses widened."


def test_finnhub_requires_a_key():
    with pytest.raises(ValueError):
        FinnhubDownloader("")


def test_client_never_exceeds_one_request_per_interval():
    gdelt = FakeGdelt()
    client = gdelt.client()

    for _ in range(3):
        client.search(
            "q",
            start=datetime(2026, 2, 1, tzinfo=UTC),
            end=datetime(2026, 2, 2, tzinfo=UTC),
        )

    gaps = [b - a for a, b in zip(gdelt.request_times, gdelt.request_times[1:])]

    assert all(gap >= 5.0 for gap in gaps)


def test_client_backs_off_and_retries_when_rate_limited():
    gdelt = FakeGdelt(responses=[RATE_LIMITED, RATE_LIMITED])

    articles = gdelt.client().search(
        "q",
        start=datetime(2026, 2, 1, tzinfo=UTC),
        end=datetime(2026, 2, 2, tzinfo=UTC),
    )

    assert len(gdelt.requests) == 3
    assert len(articles) == 1


def test_client_gives_up_when_the_limit_never_lifts():
    gdelt = FakeGdelt(responses=[RATE_LIMITED] * 10)

    with pytest.raises(GdeltRateLimited):
        gdelt.client().search(
            "q",
            start=datetime(2026, 2, 1, tzinfo=UTC),
            end=datetime(2026, 2, 2, tzinfo=UTC),
        )


def test_download_is_sliced_resumable_and_deduplicated(tmp_path):
    gdelt = FakeGdelt()
    archive = NewsArchive(tmp_path)
    source = gdelt.downloader()

    window = {
        "start": datetime(2026, 2, 1, tzinfo=UTC),
        "end": datetime(2026, 2, 27, tzinfo=UTC),
        "now": datetime(2026, 9, 19, tzinfo=UTC),
    }

    added = archive.download(source, "bac", "Bank of America Corporation", **window)

    # 27 days in 7-day slices, each a separate request
    # sorted by relevance and capped at GDELT's maximum.
    assert added == len(gdelt.requests) == 4
    assert {r["sort"] for r in gdelt.requests} == {"hybridrel"}
    assert {r["maxrecords"] for r in gdelt.requests} == {"250"}

    # Running again costs nothing.
    assert archive.download(source, "BAC", "Bank of America Corporation", **window) == 0
    assert len(gdelt.requests) == 4

    # A wider window only requests the slices it lacks.
    window["end"] = datetime(2026, 3, 6, tzinfo=UTC)

    assert archive.download(source, "BAC", "Bank of America Corporation", **window) == 1
    assert len(gdelt.requests) == 5


def test_open_slice_is_downloaded_again_next_time(tmp_path):
    gdelt = FakeGdelt()
    archive = NewsArchive(tmp_path)
    source = gdelt.downloader()

    window = {
        "start": datetime(2026, 9, 14, tzinfo=UTC),
        "end": datetime(2026, 9, 30, tzinfo=UTC),
        "now": datetime(2026, 9, 19, tzinfo=UTC),
    }

    archive.download(source, "BAC", "Bank of America Corporation", **window)
    first = len(gdelt.requests)

    # The current week is not over: news will still arrive.
    archive.download(source, "BAC", "Bank of America Corporation", **window)

    assert len(gdelt.requests) == first + 1

    # Nothing is requested for slices that lie in the future.
    assert all(r["startdatetime"] <= "20260919" for r in gdelt.requests)


def test_source_serves_the_archive_without_touching_the_network(tmp_path):
    gdelt = FakeGdelt()

    NewsArchive(tmp_path).download(
        gdelt.downloader(),
        "BAC",
        "Bank of America Corporation",
        start=datetime(2026, 2, 1, tzinfo=UTC),
        end=datetime(2026, 2, 27, tzinfo=UTC),
        now=datetime(2026, 9, 19, tzinfo=UTC),
    )

    requests_made = len(gdelt.requests)

    # A source has no downloader at all: it cannot reach out.
    source = ArchiveNewsSource(NewsArchive(tmp_path))

    items = source.fetch(
        "BAC",
        "Bank of America Corporation",
        start=datetime(2026, 2, 10, tzinfo=UTC),
        end=datetime(2026, 2, 20, tzinfo=UTC),
    )

    assert [item.published_at.date() for item in items] == [date(2026, 2, 15)]
    assert items[0].title == "Bank of America slips on bond losses"
    assert items[0].provider == "gdelt"
    assert source.local
    assert items[0].publisher == "news.example.com"

    assert source.fetch("NVDA", "NVIDIA Corporation") == ()
    assert len(gdelt.requests) == requests_made


def test_archive_is_merged_into_the_wire_on_every_read(tmp_path):
    gdelt = FakeGdelt()
    archive = NewsArchive(tmp_path / "archive")

    news = NewsRepository(
        tmp_path / "cache",
        (ArchiveNewsSource(archive),),
        cache_minutes=60,
    )

    assert news.get("BAC") == ()

    archive.download(
        gdelt.downloader(),
        "BAC",
        "Bank of America Corporation",
        start=datetime(2026, 2, 1, tzinfo=UTC),
        end=datetime(2026, 2, 7, tzinfo=UTC),
        now=datetime(2026, 9, 19, tzinfo=UTC),
    )

    # Visible immediately, not after the remote cache expires.
    assert len(news.get("BAC")) == 1


def test_replay_date_hides_later_sessions(tmp_path):
    def download(tickers, *, start, end):
        days = pd.bdate_range("2026-01-01", "2026-09-18")

        return (
            pd.DataFrame(
                {
                    "date": days,
                    "ticker": "AAA",
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume": 1.0,
                }
            ),
            None,
        )

    def latest(as_of):
        repository = MarketDataRepository(
            tmp_path,
            history_days=800,
            cache_minutes=60,
            as_of=as_of,
            downloader=download,
        )

        return repository.get_prices(("AAA",))["date"].max().date()

    assert latest(None) == date(2026, 9, 18)
    assert latest(date(2026, 2, 27)) == date(2026, 2, 27)

    # A replay date on a weekend resolves to the last session.
    assert latest(date(2026, 3, 1)) == date(2026, 2, 27)


def test_articles_are_fetched_once_then_replayed(tmp_path):
    class CountingFetcher:
        name = "counting"
        calls = 0

        def fetch(self, hit, *, retrieved_at):
            self.calls += 1

            return SourceDocument(
                document_id="DOC-1",
                title=hit.title,
                url=str(hit.url),
                retrieved_at=retrieved_at,
                text="Article body.",
            )

    inner = CountingFetcher()
    fetcher = CachedDocumentFetcher(inner, tmp_path)

    hit = SearchHit(
        hit_id="H1",
        task_id="T1",
        provider="gdelt",
        query="q",
        rank=1,
        title="Headline",
        url="https://news.example.com/a",
    )

    first = fetcher.fetch(hit, retrieved_at=datetime(2026, 9, 1, tzinfo=UTC))
    again = fetcher.fetch(hit, retrieved_at=datetime(2026, 9, 9, tzinfo=UTC))

    assert inner.calls == 1
    assert again == first
