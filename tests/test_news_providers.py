"""
The keyed news providers, without the network.

Each provider is given a fake `http_get` that records the URL
it was asked for and answers with a small fixture in the
provider's own format. No test here can reach a real API: the
key is a marker string whose only job is to be looked for in
places it must never appear.
"""

import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from financial_assistant.api.repositories import (
    AlphaVantageProvider,
    EodhdProvider,
    FinnhubProvider,
    GNewsProvider,
    MarketauxProvider,
    NewsApiProvider,
    NewsArchive,
    NewsProviderError,
    NewsProviderRateLimited,
)
from financial_assistant.api.repositories.eodhd import eodhd_symbol
from financial_assistant.api.repositories.news_provider import (
    parse_timestamp,
    scrub,
)


UTC = timezone.utc
KEY = "SECRET-KEY-123"

NOW = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
START = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
END = datetime(2024, 1, 5, 21, 0, tzinfo=UTC)


class FakeApi:
    """
    Stands in for a provider's API and for the wall clock.
    Sleeping advances the clock instead of waiting.
    """

    def __init__(self, body):
        self.body = body
        self.urls = []
        self.headers = []
        self.request_times = []
        self.now = 0.0

    def get(self, url, headers=None):
        self.urls.append(url)
        self.headers.append(headers or {})
        self.request_times.append(self.now)

        if isinstance(self.body, Exception):
            raise self.body

        return self.body if isinstance(self.body, str) else json.dumps(self.body)

    def sleep(self, seconds):
        self.now += seconds

    def build(self, provider, **options):
        return provider(
            KEY,
            http_get=self.get,
            sleep=self.sleep,
            clock=lambda: self.now,
            now=lambda: NOW,
            **options,
        )

    @property
    def params(self):
        query = parse_qs(urlparse(self.urls[-1]).query)

        return {name: values[0] for name, values in query.items()}


def assert_clean(items, provider_name, ticker="AAPL"):
    for item in items:
        assert item.provider == provider_name
        assert item.ticker == ticker
        assert item.news_id.startswith("NEWS-") and len(item.news_id) == 17
        assert item.published_at.tzinfo is not None
        assert item.published_at.utcoffset() == timedelta(0)
        assert KEY not in item.model_dump_json()


# -----------------------------------------------------
# Alpha Vantage
# -----------------------------------------------------


ALPHAVANTAGE_FEED = {
    "items": "4",
    "feed": [
        {
            "title": "Apple  supplier warns on demand",
            "url": "https://news.example.com/av-1",
            "time_published": "20240102T153000",
            "summary": "A supplier cut its outlook.",
            "source": "Example Wire",
        },
        {
            "title": "No timestamp",
            "url": "https://news.example.com/av-2",
            "summary": "",
            "source": "Example Wire",
        },
        {
            "title": "No link",
            "time_published": "20240102T153000",
        },
        {
            "title": "Date only",
            "url": "https://news.example.com/av-4",
            "time_published": "20240102",
        },
    ],
}


def test_alphavantage_parses_its_feed_and_sends_the_window():
    api = FakeApi(ALPHAVANTAGE_FEED)
    items = api.build(AlphaVantageProvider).fetch(
        "AAPL", "Apple Inc.", start=START, end=END
    )

    assert [item.title for item in items] == ["Apple supplier warns on demand"]
    assert items[0].published_at == datetime(2024, 1, 2, 15, 30, tzinfo=UTC)
    assert items[0].publisher == "Example Wire"
    assert items[0].summary == "A supplier cut its outlook."
    assert_clean(items, "alphavantage")

    assert api.urls[0].startswith("https://www.alphavantage.co/query?")
    assert api.params["function"] == "NEWS_SENTIMENT"
    assert api.params["tickers"] == "AAPL"
    assert api.params["time_from"] == "20240101T0930"
    assert api.params["time_to"] == "20240105T2100"
    assert api.params["apikey"] == KEY


@pytest.mark.parametrize("field", ["Note", "Information"])
def test_alphavantage_rate_limit_notice_raises_without_the_key(field):
    # Alpha Vantage quotes the caller's key in this notice.
    api = FakeApi(
        {field: f"We have detected your API key as {KEY} and our standard "
                "API rate limit is 25 requests per day."}
    )

    with pytest.raises(NewsProviderRateLimited) as raised:
        api.build(AlphaVantageProvider).fetch("AAPL", "Apple Inc.")

    assert "25 requests per day" in str(raised.value)
    assert KEY not in str(raised.value)


def test_alphavantage_does_not_spend_a_request_on_a_foreign_symbol():
    api = FakeApi(ALPHAVANTAGE_FEED)

    assert api.build(AlphaVantageProvider).fetch("NESN.SW", "Nestle") == []
    assert api.urls == []


# -----------------------------------------------------
# EODHD
# -----------------------------------------------------


@pytest.mark.parametrize(
    "yahoo, eodhd",
    [
        ("AAPL", "AAPL.US"),
        ("aapl", "AAPL.US"),
        ("BRK-B", "BRK-B.US"),
        ("SAP.DE", "SAP.XETRA"),
        ("SHEL.L", "SHEL.LSE"),
        ("MC.PA", "MC.PA"),
        ("NESN.SW", "NESN.SW"),
        ("NOVO-B.CO", "NOVO-B.CO"),
        ("7203.T", "7203.T"),
    ],
)
def test_eodhd_symbols_are_exchange_qualified(yahoo, eodhd):
    assert eodhd_symbol(yahoo) == eodhd


def test_eodhd_parses_its_rows_and_sends_the_window():
    api = FakeApi(
        [
            {
                "date": "2024-01-02T15:30:00+00:00",
                "title": "SAP raises cloud outlook",
                "content": "word " * 200,
                "link": "https://news.example.com/eodhd-1",
                "symbols": ["SAP.XETRA"],
            },
            {
                "date": "2024-01-02T10:00:00-05:00",
                "title": "Stamped in New York",
                "content": "",
                "link": "https://news.example.com/eodhd-2",
            },
            {"date": None, "title": "Undated", "link": "https://x.example.com/3"},
            {"date": "2024-01-02T15:30:00+00:00", "title": "No link", "link": ""},
        ]
    )

    items = api.build(EodhdProvider).fetch("SAP.DE", "SAP SE", start=START, end=END)

    assert [item.title for item in items] == [
        "SAP raises cloud outlook",
        "Stamped in New York",
    ]
    assert len(items[0].summary) <= 400 and items[0].summary.startswith("word word")
    assert items[1].published_at == datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
    assert_clean(items, "eodhd", ticker="SAP.DE")

    assert api.urls[0].startswith("https://eodhd.com/api/news?")
    assert api.params["s"] == "SAP.XETRA"
    assert api.params["from"] == "2024-01-01"
    assert api.params["to"] == "2024-01-05"
    assert api.params["fmt"] == "json"


# -----------------------------------------------------
# Finnhub
# -----------------------------------------------------


FINNHUB_ROWS = [
    {
        "headline": "Apple  unveils headset",
        "url": "https://news.example.com/finnhub-1",
        "datetime": 1704209400,
        "source": "Example Wire",
        "summary": "It ships in February.",
    },
    {"headline": "Undated", "url": "https://news.example.com/finnhub-2", "datetime": 0},
    {"headline": "", "url": "https://news.example.com/finnhub-3", "datetime": 1704209400},
]


def test_finnhub_is_a_live_source_with_a_default_window():
    api = FakeApi(FINNHUB_ROWS)
    items = api.build(FinnhubProvider).fetch("AAPL", "Apple Inc.")

    assert [item.title for item in items] == ["Apple unveils headset"]
    assert items[0].published_at == datetime(2024, 1, 2, 15, 30, tzinfo=UTC)
    assert_clean(items, "finnhub")

    # Nobody chose dates: the last fourteen days.
    assert api.params["symbol"] == "AAPL"
    assert api.params["from"] == "2023-12-27"
    assert api.params["to"] == "2024-01-10"


def test_finnhub_window_never_reaches_into_the_future():
    api = FakeApi(FINNHUB_ROWS)

    api.build(FinnhubProvider).fetch(
        "AAPL", "Apple Inc.", start=START, end=NOW + timedelta(days=3)
    )

    assert api.params["from"] == "2024-01-01"
    assert api.params["to"] == "2024-01-10"


def test_finnhub_skips_symbols_it_does_not_cover():
    api = FakeApi(FINNHUB_ROWS)

    assert api.build(FinnhubProvider).fetch("NESN.SW", "Nestle") == []
    assert api.urls == []


def test_finnhub_error_body_raises():
    api = FakeApi({"error": "API limit reached. Please try again later."})

    with pytest.raises(NewsProviderRateLimited):
        api.build(FinnhubProvider).fetch("AAPL", "Apple Inc.")


# -----------------------------------------------------
# GNews
# -----------------------------------------------------


GNEWS_ARTICLES = {
    "totalArticles": 4,
    "articles": [
        {
            "title": "Apple faces new antitrust complaint",
            "description": "Regulators are looking at the App Store.",
            "url": "https://news.example.com/gnews-1",
            "publishedAt": "2024-01-02T15:30:00Z",
            "source": {"name": "Example Wire", "url": "https://news.example.com"},
        },
        {
            "title": "Ten apple pie recipes for winter",
            "description": "Bake with what is in season.",
            "url": "https://news.example.com/gnews-2",
            "publishedAt": "2024-01-02T16:00:00Z",
            "source": {"name": "Example Kitchen"},
        },
        {
            "title": "Apple without a date",
            "url": "https://news.example.com/gnews-3",
            "source": {"name": "Example Wire"},
        },
        {
            "title": "Apple without a link",
            "publishedAt": "2024-01-02T15:30:00Z",
        },
    ],
}


def test_gnews_parses_articles_and_keeps_only_stories_about_the_company():
    api = FakeApi(GNEWS_ARTICLES)
    items = api.build(GNewsProvider).fetch("AAPL", "Apple Inc.", start=START, end=END)

    # "apple pie" matched the text search, not the company.
    assert [item.title for item in items] == ["Apple faces new antitrust complaint"]
    assert items[0].publisher == "Example Wire"
    assert items[0].summary == "Regulators are looking at the App Store."
    assert_clean(items, "gnews")

    assert api.urls[0].startswith("https://gnews.io/api/v4/search?")
    assert api.params["q"] == '"Apple" OR AAPL'
    assert api.params["from"] == "2024-01-01T09:30:00Z"
    assert api.params["to"] == "2024-01-05T21:00:00Z"
    assert api.params["lang"] == "en"


def test_gnews_error_body_raises():
    api = FakeApi({"errors": ["You have reached your request limit for today."]})

    with pytest.raises(NewsProviderError) as raised:
        api.build(GNewsProvider).fetch("AAPL", "Apple Inc.")

    assert "request limit" in str(raised.value)


def test_text_matched_providers_record_their_query_in_the_signature():
    gnews = FakeApi(GNEWS_ARTICLES).build(GNewsProvider)

    assert gnews.signature("AAPL", "Apple Inc.") != gnews.signature("AAPL", "AAPL")
    assert gnews.signature("AAPL", "Apple Inc.") == gnews.signature("AAPL", "Apple Inc.")


# -----------------------------------------------------
# Marketaux
# -----------------------------------------------------


def test_marketaux_parses_data_and_sends_the_window():
    api = FakeApi(
        {
            "meta": {"found": 3, "returned": 3},
            "data": [
                {
                    "title": "Apple supplier shifts output to India",
                    "description": "",
                    "snippet": "The move follows new tariffs.",
                    "url": "https://news.example.com/marketaux-1",
                    "published_at": "2024-01-02T15:30:00.000000Z",
                    "source": "example.com",
                },
                {
                    "title": "Undated",
                    "url": "https://news.example.com/marketaux-2",
                    "published_at": "",
                },
                {"title": "No link", "published_at": "2024-01-02T15:30:00.000000Z"},
            ],
        }
    )

    items = api.build(MarketauxProvider).fetch(
        "AAPL", "Apple Inc.", start=START, end=END
    )

    assert [item.title for item in items] == ["Apple supplier shifts output to India"]
    assert items[0].summary == "The move follows new tariffs."
    assert items[0].publisher == "example.com"
    assert items[0].published_at == datetime(2024, 1, 2, 15, 30, tzinfo=UTC)
    assert_clean(items, "marketaux")

    assert api.urls[0].startswith("https://api.marketaux.com/v1/news/all?")
    assert api.params["symbols"] == "AAPL"
    assert api.params["filter_entities"] == "true"
    assert api.params["published_after"] == "2024-01-01T09:30"
    assert api.params["published_before"] == "2024-01-05T21:00"


def test_marketaux_usage_limit_raises():
    api = FakeApi(
        {"error": {"code": "usage_limit_reached", "message": "Usage limit reached."}}
    )

    with pytest.raises(NewsProviderRateLimited):
        api.build(MarketauxProvider).fetch("AAPL", "Apple Inc.")


# -----------------------------------------------------
# NewsAPI
# -----------------------------------------------------


NEWSAPI_ARTICLES = {
    "status": "ok",
    "totalResults": 4,
    "articles": [
        {
            "source": {"id": None, "name": "Example Wire"},
            "title": "Bank of America shares slip on bond losses",
            "description": "Unrealised losses widened.",
            "url": "https://news.example.com/newsapi-1",
            "publishedAt": "2024-01-02T15:30:00Z",
        },
        {
            "source": {"name": "Example Wire"},
            "title": "Analysts lift targets across tech stocks",
            "description": "A Bank of Montreal analyst was the most bullish.",
            "url": "https://news.example.com/newsapi-2",
            "publishedAt": "2024-01-02T16:00:00Z",
        },
        {
            "source": {"name": "Example Wire"},
            "title": "[Removed]",
            "url": "https://removed.com",
            "publishedAt": "2024-01-02T15:30:00Z",
        },
        {
            "source": {"name": "Example Wire"},
            "title": "Bank of America, undated",
            "url": "https://news.example.com/newsapi-4",
            "publishedAt": None,
        },
    ],
}


def test_newsapi_sends_the_key_in_a_header_and_dates_in_the_query():
    api = FakeApi(NEWSAPI_ARTICLES)

    items = api.build(NewsApiProvider).fetch(
        "BAC", "Bank of America Corporation", start=START, end=END
    )

    assert [item.title for item in items] == [
        "Bank of America shares slip on bond losses"
    ]
    assert items[0].publisher == "Example Wire"
    assert_clean(items, "newsapi", ticker="BAC")

    assert api.urls[0].startswith("https://newsapi.org/v2/everything?")
    assert KEY not in api.urls[0]
    assert api.headers[0] == {"X-Api-Key": KEY}

    assert api.params["q"].startswith('"Bank of America" AND (')
    assert api.params["from"] == "2024-01-01T09:30:00"
    assert api.params["to"] == "2024-01-05T21:00:00"
    assert api.params["sortBy"] == "publishedAt"


def test_newsapi_never_asks_for_more_history_than_the_plan_has():
    api = FakeApi(NEWSAPI_ARTICLES)
    provider = api.build(NewsApiProvider)

    provider.fetch(
        "BAC",
        "Bank of America Corporation",
        start=NOW - timedelta(days=60),
        end=NOW,
    )

    assert api.params["from"] == "2023-12-12T12:00:00"

    # A slice entirely out of reach is not asked for at all.
    assert provider.fetch(
        "BAC",
        "Bank of America Corporation",
        start=NOW - timedelta(days=90),
        end=NOW - timedelta(days=60),
    ) == []
    assert len(api.urls) == 1


def test_newsapi_error_status_raises():
    api = FakeApi(
        {
            "status": "error",
            "code": "rateLimited",
            "message": "You have made too many requests recently.",
        }
    )

    with pytest.raises(NewsProviderRateLimited) as raised:
        api.build(NewsApiProvider).fetch("BAC", "Bank of America Corporation")

    assert "too many requests" in str(raised.value)


# -----------------------------------------------------
# All of them
# -----------------------------------------------------


PROVIDERS = [
    AlphaVantageProvider,
    EodhdProvider,
    FinnhubProvider,
    GNewsProvider,
    MarketauxProvider,
    NewsApiProvider,
]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_provider_is_not_built_without_its_key(provider):
    with pytest.raises(ValueError) as raised:
        provider("")

    assert provider.key_variable in str(raised.value)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_key_never_leaks_into_an_error(provider):
    leaky = f"https://api.example.com/news?symbol=AAPL&token={KEY}&apikey={KEY}"

    failures = [
        # urllib, requests and proxies all like to quote the URL.
        OSError(f"connection refused for url: {leaky}"),
        HTTPError(leaky, 429, "Too Many Requests", {}, None),
        HTTPError(leaky, 500, f"Server Error for {leaky}", {}, None),
        f"<html>Bad gateway while fetching {leaky}</html>",
    ]

    for failure in failures:
        api = FakeApi(failure)

        with pytest.raises(NewsProviderError) as raised:
            api.build(provider).fetch("AAPL", "Apple Inc.")

        assert KEY not in str(raised.value)
        assert KEY not in repr(raised.value)
        assert provider.name in str(raised.value)

        # Nothing chained either: a traceback prints causes.
        assert raised.value.__cause__ is None
        assert raised.value.__suppress_context__


def test_http_429_is_a_rate_limit():
    api = FakeApi(HTTPError("https://x.example.com", 429, "Too Many Requests", {}, None))

    with pytest.raises(NewsProviderRateLimited):
        api.build(MarketauxProvider).fetch("AAPL", "Apple Inc.")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_requests_to_one_provider_are_spaced(provider):
    api = FakeApi({"feed": [], "articles": [], "data": [], "status": "ok"})

    if provider in (EodhdProvider, FinnhubProvider):
        api.body = []

    built = api.build(provider)

    for _ in range(3):
        built.fetch("AAPL", "Apple Inc.")

    gaps = [
        later - earlier
        for earlier, later in zip(api.request_times, api.request_times[1:])
    ]

    assert len(gaps) == 2
    assert min(gaps) >= provider.min_interval_seconds


def test_budgets_are_declared_and_can_be_raised_for_a_paid_plan():
    assert AlphaVantageProvider.daily_budget == 25
    assert FinnhubProvider.daily_budget is None

    paid = FakeApi([]).build(EodhdProvider, daily_budget=5000, min_refresh_minutes=30)

    assert (paid.daily_budget, paid.min_refresh_minutes) == (5000, 30)
    assert EodhdProvider.daily_budget == 2


def test_every_provider_can_fill_the_archive(tmp_path):
    api = FakeApi(ALPHAVANTAGE_FEED)
    archive = NewsArchive(tmp_path)

    window = {"start": START, "end": END, "now": NOW}
    provider = api.build(AlphaVantageProvider)

    assert archive.download(provider, "AAPL", "Apple Inc.", **window) == 1
    assert archive.download(provider, "AAPL", "Apple Inc.", **window) == 0

    assert [item.provider for item in archive.read("AAPL")] == ["alphavantage"]


def test_timestamps_must_be_complete():
    assert parse_timestamp("2024-01-02") is None
    assert parse_timestamp("") is None
    assert parse_timestamp(None) is None
    assert parse_timestamp(0) is None
    assert parse_timestamp("not a date at all") is None

    # No zone given: the providers that omit it mean UTC.
    assert parse_timestamp("2024-01-02 15:30:00") == datetime(
        2024, 1, 2, 15, 30, tzinfo=UTC
    )


def test_scrub_cuts_query_strings_and_masks_the_key():
    text = scrub(
        f"GET https://api.example.com/v1/news?token={KEY} failed; key {KEY}",
        KEY,
    )

    assert text == "GET https://api.example.com/v1/news failed; key ***"
