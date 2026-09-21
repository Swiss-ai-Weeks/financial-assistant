"""
The news cache: what the desk answers from, and how carefully
it spends other people's quotas.

Time is a value the test moves by hand, sources are fakes that
count how often they were asked, and a background refresh is
held open with an Event so that "answered before the refresh
finished" is something the test can actually observe.
"""

import json
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from financial_assistant.api import dependencies as deps
from financial_assistant.api.controllers import news_controller
from financial_assistant.api.models import NewsItem
from financial_assistant.api.repositories import (
    NewsProviderRateLimited,
    NewsRepository,
)
from financial_assistant.api.services import NewsService


UTC = timezone.utc
KEY = "SECRET-KEY-123"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


class FakeSource:
    """
    Every fetch returns one more story than the last, so a
    test can tell how many fetches a feed is made of.
    """

    local = False

    def __init__(self, name, *, min_refresh_minutes=None, daily_budget=None):
        self.name = name
        self.calls = []
        self.error = None

        self.gate = None
        self.started = threading.Event()

        if min_refresh_minutes is not None:
            self.min_refresh_minutes = min_refresh_minutes

        if daily_budget is not None:
            self.daily_budget = daily_budget

    def fetch(self, ticker, company, *, start=None, end=None):
        self.calls.append(ticker)
        self.started.set()

        if self.gate is not None:
            assert self.gate.wait(timeout=5)

        if self.error is not None:
            raise self.error

        return tuple(
            NewsItem(
                news_id=f"NEWS-{self.name}-{ticker}-{number}",
                ticker=ticker,
                title=f"{ticker} story {number} from {self.name}",
                url=f"https://news.example.com/{self.name}/{ticker}/{number}",
                published_at=datetime(2026, 9, 1, tzinfo=UTC)
                + timedelta(hours=number),
                provider=self.name,
            )
            for number in range(1, len(self.calls) + 1)
        )


def repository(tmp_path, clock, *sources, **options):
    options.setdefault("background", False)

    return NewsRepository(
        tmp_path / "news",
        tuple(sources),
        cache_minutes=30,
        now=clock,
        **options,
    )


def status_of(news, name):
    return next(row for row in news.status() if row.name == name)


def wait_until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        if condition():
            return True

        time.sleep(0.01)

    return False


# -----------------------------------------------------
# Stale-while-revalidate
# -----------------------------------------------------


def test_first_request_waits_then_the_cache_answers(tmp_path):
    clock = Clock()
    wire = FakeSource("wire")
    news = repository(tmp_path, clock, wire, background=True)

    # Nothing cached: there is nothing to answer with but the fetch.
    assert len(news.get("bac")) == 1
    assert wire.calls == ["BAC"]

    # Fresh: nobody is asked.
    clock.advance(minutes=29)

    assert len(news.get("BAC")) == 1
    assert wire.calls == ["BAC"]


def test_stale_cache_is_served_at_once_and_refreshed_behind_the_request(tmp_path):
    clock = Clock()
    wire = FakeSource("wire")
    news = repository(tmp_path, clock, wire, background=True)

    news.get("BAC")
    clock.advance(minutes=31)

    wire.gate = threading.Event()
    wire.started.clear()

    # The refresh is held open, and get() returns anyway,
    # with what was already known.
    assert len(news.get("BAC")) == 1
    assert wire.started.wait(timeout=5)

    # Asking again while it runs starts nothing new.
    assert len(news.get("BAC")) == 1
    assert len(news.get("BAC")) == 1

    wire.gate.set()

    assert wait_until(lambda: len(news.get("BAC")) == 2)
    assert wire.calls == ["BAC", "BAC"]


def test_a_failing_background_refresh_never_reaches_the_request(tmp_path):
    clock = Clock()
    wire = FakeSource("wire")
    news = repository(tmp_path, clock, wire, background=True)

    news.get("BAC")
    clock.advance(minutes=31)

    wire.error = RuntimeError("wire is down")

    assert len(news.get("BAC")) == 1
    assert wait_until(lambda: status_of(news, "wire").last_error == "wire is down")
    assert len(news.get("BAC")) == 1


# -----------------------------------------------------
# Intervals and budgets
# -----------------------------------------------------


def test_each_source_is_refreshed_at_its_own_pace(tmp_path):
    clock = Clock()
    quick = FakeSource("quick")
    scarce = FakeSource("scarce", min_refresh_minutes=12 * 60)
    news = repository(tmp_path, clock, quick, scarce)

    news.get("BAC")
    assert (len(quick.calls), len(scarce.calls)) == (1, 1)

    # `cache_minutes` paces a source that declares nothing.
    clock.advance(minutes=31)
    news.get("BAC")
    assert (len(quick.calls), len(scarce.calls)) == (2, 1)

    # The interval is per ticker: another ticker is new to both.
    news.get("JPM")
    assert (len(quick.calls), len(scarce.calls)) == (3, 2)

    clock.advance(hours=12)
    news.get("BAC")
    assert (len(quick.calls), len(scarce.calls)) == (4, 3)


def test_daily_budget_is_shared_by_all_tickers_and_survives_a_restart(tmp_path):
    clock = Clock()
    scarce = FakeSource("scarce", min_refresh_minutes=0, daily_budget=3)
    news = repository(tmp_path, clock, scarce)

    for ticker in ("BAC", "JPM", "WFC", "C", "GS"):
        news.get(ticker)

    assert scarce.calls == ["BAC", "JPM", "WFC"]
    assert status_of(news, "scarce").requests_today == 3
    assert status_of(news, "scarce").daily_budget == 3

    # A restarted desk reads what the last one spent.
    restarted_source = FakeSource("scarce", min_refresh_minutes=0, daily_budget=3)
    restarted = repository(tmp_path, clock, restarted_source)

    restarted.get("GS")
    restarted.get("BAC", force=True)

    assert restarted_source.calls == []
    assert status_of(restarted, "scarce").requests_today == 3
    assert len(restarted.get("BAC")) == 1

    # Tomorrow there is quota again.
    clock.advance(days=1)

    assert status_of(restarted, "scarce").requests_today == 0

    restarted.get("GS")

    assert restarted_source.calls == ["GS"]
    assert status_of(restarted, "scarce").requests_today == 1


def test_a_failed_request_still_counts(tmp_path):
    clock = Clock()
    scarce = FakeSource("scarce", min_refresh_minutes=60, daily_budget=5)
    scarce.error = RuntimeError("down")
    news = repository(tmp_path, clock, scarce)

    news.get("BAC")
    news.get("BAC")

    # Not asked again inside the interval just because it failed.
    assert scarce.calls == ["BAC"]
    assert status_of(news, "scarce").requests_today == 1


def test_a_rate_limited_source_is_left_alone_for_a_while(tmp_path):
    clock = Clock()
    limited = FakeSource("limited", min_refresh_minutes=0)
    limited.error = NewsProviderRateLimited("limited: quota spent")
    news = repository(tmp_path, clock, limited)

    news.get("BAC")
    news.get("JPM")
    news.get("BAC", force=True)

    assert limited.calls == ["BAC"]

    clock.advance(minutes=61)
    limited.error = None

    assert len(news.get("JPM")) == 2
    assert status_of(news, "limited").last_error is None


# -----------------------------------------------------
# Isolation, force, status
# -----------------------------------------------------


def test_one_dead_source_does_not_blank_the_feed(tmp_path):
    clock = Clock()
    dead = FakeSource("dead")
    alive = FakeSource("alive")

    dead.error = OSError(
        f"timed out: https://api.example.com/news?symbol=BAC&token={KEY}"
    )

    news = repository(tmp_path, clock, dead, alive, unconfigured=("eodhd",))

    assert [item.provider for item in news.get("BAC")] == ["alive"]

    failed = status_of(news, "dead")

    assert failed.last_attempt == clock.now
    assert failed.last_success is None
    assert failed.last_error == "timed out: https://api.example.com/news"
    assert failed.articles == 0

    worked = status_of(news, "alive")

    assert worked.last_success == clock.now
    assert worked.last_error is None
    assert worked.articles == 1
    assert worked.configured and not worked.local

    # Known to the desk, but without a key.
    assert not status_of(news, "eodhd").configured

    # The key is nowhere on disk.
    for path in (tmp_path / "news").iterdir():
        assert KEY not in path.read_text()


def test_force_refresh_ignores_the_interval_and_waits(tmp_path):
    clock = Clock()
    wire = FakeSource("wire", min_refresh_minutes=24 * 60)
    news = repository(tmp_path, clock, wire, background=True)

    assert len(news.get("BAC")) == 1
    assert len(news.get("BAC")) == 1
    assert len(news.get("BAC", force=True)) == 2

    assert wire.calls == ["BAC", "BAC"]
    assert status_of(news, "wire").articles == 2


def test_first_source_to_report_a_story_keeps_it(tmp_path):
    clock = Clock()

    class Slow(FakeSource):
        def fetch(self, ticker, company, *, start=None, end=None):
            items = super().fetch(ticker, company, start=start, end=end)

            return tuple(
                item.model_copy(update={"news_id": "NEWS-shared"})
                for item in items
            )

    first = Slow("first")
    second = Slow("second")

    # `first` answers last, and is still the one kept.
    first.gate = threading.Event()

    news = repository(tmp_path, clock, first, second)

    threading.Timer(0.05, first.gate.set).start()

    assert [item.provider for item in news.get("BAC")] == ["first"]


def test_cache_files_are_plain_json_next_to_a_meta_file(tmp_path):
    clock = Clock()
    news = repository(tmp_path, clock, FakeSource("wire", daily_budget=10))

    news.get("BAC")

    directory = tmp_path / "news"

    assert sorted(path.name for path in directory.iterdir()) == [
        "BAC.json",
        "_meta.json",
    ]

    meta = json.loads((directory / "_meta.json").read_text())

    assert meta["sources"]["wire"]["requests_today"] == 1
    assert meta["sources"]["wire"]["day"] == "2026-09-21"


# -----------------------------------------------------
# HTTP
# -----------------------------------------------------


class NoPortfolio:
    def load(self):
        class Empty:
            tickers = ()
            positions = ()

        return Empty()


class NoInstruments:
    def describe(self, ticker):
        class Unknown:
            name = ticker

        return Unknown()


def test_sources_and_refresh_endpoints(tmp_path):
    wire = FakeSource("wire", min_refresh_minutes=24 * 60, daily_budget=25)

    # The real clock: the service filters on the real window.
    news = NewsRepository(
        tmp_path / "news",
        (wire,),
        cache_minutes=30,
        background=False,
        unconfigured=("gnews",),
    )

    original = FakeSource.fetch

    def recent(self, ticker, company, *, start=None, end=None):
        return tuple(
            item.model_copy(
                update={
                    "published_at": datetime.now(UTC) - timedelta(hours=number)
                }
            )
            for number, item in enumerate(
                original(self, ticker, company, start=start, end=end), start=1
            )
        )

    wire.fetch = recent.__get__(wire)

    app = FastAPI()
    app.include_router(news_controller.router, prefix="/api")

    app.dependency_overrides[deps.get_news_service] = lambda: NewsService(
        news, NoPortfolio(), NoInstruments(), review_days=30
    )

    client = TestClient(app)

    assert len(client.get("/api/news/BAC").json()) == 1
    assert len(client.get("/api/news/BAC").json()) == 1

    refreshed = client.post("/api/news/BAC/refresh")

    assert refreshed.status_code == 200
    assert len(refreshed.json()) == 2

    # "sources" is not a ticker.
    rows = {row["name"]: row for row in client.get("/api/news/sources").json()}

    assert wire.calls == ["BAC", "BAC"]
    assert set(rows) == {"wire", "gnews"}

    assert rows["wire"]["configured"] is True
    assert rows["wire"]["local"] is False
    assert rows["wire"]["requests_today"] == 2
    assert rows["wire"]["daily_budget"] == 25
    assert rows["wire"]["articles"] == 2
    assert rows["wire"]["last_success"] is not None
    assert rows["wire"]["last_error"] is None

    assert rows["gnews"]["configured"] is False
