"""
What every keyed news API has in common.

    NewsProviderError        anything a provider can fail with
    NewsProviderRateLimited  the quota is spent, asking again is pointless
    KeyedNewsProvider        one throttled request, parsed into NewsItems

A provider is BOTH a live source for the desk (NewsSource:
"whatever is recent") and a downloader for the archive
(NewsDownloader: "this slice of history"). The two differ only
in who chooses the dates, so they share one request and one
parser and a subclass only says how to ask and how to read a
row.

API keys travel in query strings. Nothing that leaves this
module (exceptions, and through them logs, cache files and the
status endpoint) may contain one, so every error message is
scrubbed before it is raised.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from financial_assistant.api.models import NewsItem


TIMEOUT_SECONDS = 20

# With no dates given, a live source reads this far back.
LIVE_WINDOW_DAYS = 14

# HTTP statuses the providers use for "quota spent": 429
# everywhere, 402 at EODHD and Marketaux, 426 at NewsAPI
# when the plan does not reach that far back.
RATE_LIMIT_STATUSES = {402, 426, 429}

_URL_QUERY = re.compile(r"(https?://[^\s?'\"<>]+)\?[^\s'\"<>]*")


class NewsProviderError(RuntimeError):
    """A news provider could not answer. Never contains a key."""


class NewsProviderRateLimited(NewsProviderError):
    """The provider refused because a quota is spent."""


def news_id(url: str) -> str:
    return "NEWS-" + sha1(url.encode("utf-8")).hexdigest()[:12]


def scrub(text: str, *secrets: str | None) -> str:
    """
    Make an error message safe to show: query strings are
    cut from URLs and the key itself is masked wherever
    else it appears. Alpha Vantage, for one, quotes the
    caller's key back in its rate limit notice.
    """

    text = _URL_QUERY.sub(r"\1", " ".join(str(text).split()))

    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")

    return text[:300]


def parse_timestamp(value) -> datetime | None:
    """
    A FULL timestamp as timezone-aware UTC, or None.

    A bare date is refused on purpose: a headline that
    cannot be placed before or after a session close
    cannot be admitted as evidence for it.
    """

    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc)

    if not isinstance(value, str) or len(value.strip()) <= 10:
        return None

    text = value.strip()

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None

        # Alpha Vantage: 20240102T153000, or without seconds.
        for pattern in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def http_get(url: str, headers: dict[str, str] | None = None) -> str:
    request = Request(
        url,
        headers={"User-Agent": "ClaimGraph/0.3", **(headers or {})},
    )

    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


class KeyedNewsProvider:
    """
    Base of the providers that need an API key.

    A subclass declares its limits as class attributes and
    implements `_request` (URL and headers for a window) and
    `_parse` (one JSON body into rows of title, url, time).

    The limits are the free tier's, because that is what a
    fresh checkout runs on. Both can be raised per instance
    by whoever pays for more.
    """

    name: str
    local = False

    # Named in the error when the key is missing.
    key_variable: str

    # Seconds between two requests to this provider.
    min_interval_seconds: float = 1.1

    # Read by NewsRepository: how often one ticker may be
    # refreshed, and how many requests a day may be spent
    # across all tickers.
    min_refresh_minutes: int = 60
    daily_budget: int | None = None

    # How far back the plan reaches. Asking for more is an
    # error at some providers, so the window is clamped.
    max_history_days: int | None = None

    # Part of the archive signature: bump when the query
    # changes so old slices are downloaded again.
    version = "v1"

    def __init__(
        self,
        api_key: str,
        *,
        http_get: Callable[..., str] = http_get,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        min_refresh_minutes: int | None = None,
        daily_budget: int | None = None,
    ):
        if not api_key:
            raise ValueError(f"{self.key_variable} is not configured")

        self._api_key = api_key
        self._http_get = http_get
        self._sleep = sleep
        self._clock = clock
        self._now = now

        if min_refresh_minutes is not None:
            self.min_refresh_minutes = min_refresh_minutes

        if daily_budget is not None:
            self.daily_budget = daily_budget

        self._lock = threading.Lock()
        self._last_request: float | None = None

    # -------------------------------------------------
    # NewsDownloader and NewsSource
    # -------------------------------------------------

    def signature(self, ticker: str, company: str) -> str:
        # Queried by symbol only, so there is nothing to vary.
        return self.version

    def covers(self, ticker: str) -> bool:
        """
        Whether the provider knows this kind of symbol at
        all. Asking anyway would spend quota on an error.
        """

        return True

    def fetch(
        self,
        ticker: str,
        company: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NewsItem]:
        now = self._now()

        # The desk's window runs a few days past the last
        # session. Providers have nothing there, and some
        # reject a date in the future.
        end = min(end or now, now)
        start = start or end - timedelta(days=LIVE_WINDOW_DAYS)

        if self.max_history_days is not None:
            start = max(start, now - timedelta(days=self.max_history_days))

        if start >= end or not self.covers(ticker):
            return []

        url, headers = self._request(ticker, company, start, end)
        items: dict[str, NewsItem] = {}

        for row in self._parse(self._get_json(url, headers)):
            link = row.get("url")
            title = " ".join(str(row.get("title") or "").split())
            published_at = parse_timestamp(row.get("published_at"))

            if not link or not title or published_at is None:
                continue

            item = NewsItem(
                news_id=news_id(link),
                ticker=ticker,
                title=title,
                url=link,
                publisher=row.get("publisher") or None,
                published_at=published_at,
                summary=" ".join(str(row.get("summary") or "").split()),
                provider=self.name,
            )

            if self._keep(item, ticker, company):
                items.setdefault(item.news_id, item)

        return list(items.values())

    # -------------------------------------------------
    # For subclasses
    # -------------------------------------------------

    def _request(
        self,
        ticker: str,
        company: str,
        start: datetime,
        end: datetime,
    ) -> tuple[str, dict[str, str]]:
        raise NotImplementedError

    def _parse(self, payload) -> list[dict]:
        raise NotImplementedError

    def _keep(self, item: NewsItem, ticker: str, company: str) -> bool:
        return True

    # -------------------------------------------------

    def _get_json(self, url: str, headers: dict[str, str]):
        with self._lock:
            if self._last_request is not None:
                remaining = self.min_interval_seconds - (
                    self._clock() - self._last_request
                )

                if remaining > 0:
                    self._sleep(remaining)

            self._last_request = self._clock()

            try:
                # Only a provider that sends headers needs an
                # http_get that accepts them.
                body = (
                    self._http_get(url, headers)
                    if headers
                    else self._http_get(url)
                )

            except HTTPError as error:
                kind = (
                    NewsProviderRateLimited
                    if error.code in RATE_LIMIT_STATUSES
                    else NewsProviderError
                )

                # `from None`: the original carries the URL,
                # and with it the key, into any traceback.
                raise kind(
                    f"{self.name}: HTTP {error.code} "
                    f"{self._scrub(error.reason)}"
                ) from None

            except NewsProviderError:
                raise

            except Exception as error:
                raise NewsProviderError(
                    f"{self.name}: {self._scrub(error)}"
                ) from None

        try:
            return json.loads(body)
        except ValueError:
            raise NewsProviderError(
                f"{self.name}: unreadable response: {self._scrub(body[:200])}"
            ) from None

    def _scrub(self, text) -> str:
        return scrub(str(text), self._api_key)

    def _refused(self, message, *, rate_limited: bool = False):
        kind = NewsProviderRateLimited if rate_limited else NewsProviderError

        return kind(f"{self.name}: {self._scrub(message)}")
