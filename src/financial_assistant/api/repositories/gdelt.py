"""
GDELT DOC 2.0 as a provider for the news archive.

    GdeltClient        throttled access to the API
    GdeltDownloader    NewsDownloader: one slice of history

GDELT reaches back to 2017 and needs no key, at the price of
a strict rate limit, noisy text matching and no summaries.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha1
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from financial_assistant.api.models import NewsItem
from financial_assistant.api.relevance import company_phrase


ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT returns at most 250 articles per request. A busy
# name exceeds that within days, which is why the archive
# downloads in weekly slices and each request is sorted by
# relevance rather than by date.
MAX_RECORDS = 250

MIN_INTERVAL_SECONDS = 5.5
RATE_LIMIT_MARKER = "limit requests"
RATE_LIMIT_NOTICE = "Please limit requests to one every 5 seconds."
MAX_ATTEMPTS = 6

# Narrows a company name to coverage an investor would read.
FINANCE_TERMS = "(shares OR stock OR earnings OR investors OR analysts)"

# Sites that mass-produce templated articles from filings
# and price feeds ("X LLC increases stake in ..."). Measured
# on a real download they were 88% of the results for a large
# bank, and GDELT caps every request at 250 articles, so they
# have to be excluded in the query itself or they crowd out
# the journalism. They are filtered again on read, which also
# covers archives downloaded before a site was listed.
#
# Ordered worst first: GDELT rejects long queries ("Your
# query was too short or too long"), so only as many
# exclusions as fit MAX_QUERY_CHARS go into the query.
CONTENT_FARMS = (
    "themarketsdaily.com",
    "dailypolitical.com",
    "tickerreport.com",
    "americanbankingnews.com",
    "marketbeat.com",
    "etfdailynews.com",
    "watchlistnews.com",
    "thelincolnianonline.com",
)

MAX_QUERY_CHARS = 200


class GdeltRateLimited(RuntimeError):
    """GDELT kept refusing after every retry."""


class GdeltRejected(RuntimeError):
    """GDELT answered with an explanation instead of results."""


def _http_get(url: str) -> str:
    """
    GDELT announces its rate limit in two ways: HTTP 429, or
    HTTP 200 with a plain-text notice. Both are returned as
    text so the caller has one case to handle.
    """

    request = Request(url, headers={"User-Agent": "ClaimGraph/0.3"})

    try:
        with urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")

    except HTTPError as error:
        if error.code == 429:
            return RATE_LIMIT_NOTICE

        raise


def build_query(ticker: str, company: str) -> str:
    """
    GDELT matches text, not tickers, so the query is the
    company's written name. A bare ticker is only used
    when no name is known.
    """

    phrase = company_phrase(ticker, company)
    subject = f'"{phrase}"' if " " in phrase else phrase

    query = f"{subject} {FINANCE_TERMS} sourcelang:english"

    for domain in CONTENT_FARMS:
        longer = f"{query} -domain:{domain}"

        if len(longer) > MAX_QUERY_CHARS:
            break

        query = longer

    return query


class GdeltClient:
    """
    One throttled request at a time, process-wide.
    """

    def __init__(
        self,
        *,
        http_get: Callable[[str], str] = _http_get,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = MIN_INTERVAL_SECONDS,
    ):
        self._http_get = http_get
        self._sleep = sleep
        self._clock = clock
        self._min_interval = min_interval

        self._lock = threading.Lock()
        self._last_request: float | None = None

    def search(
        self,
        query: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        params = urlencode(
            {
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": MAX_RECORDS,
                "sort": "hybridrel",
                "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                "enddatetime": end.strftime("%Y%m%d%H%M%S"),
            }
        )

        with self._lock:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                self._wait_for_slot()
                body = self._http_get(f"{ENDPOINT}?{params}")

                # The limit is announced as plain text with
                # HTTP 200, not as an error status.
                if RATE_LIMIT_MARKER in body[:300].lower():
                    self._sleep(self._min_interval * attempt)
                    continue

                # No match is an empty body or an empty object.
                if not body.strip():
                    return []

                # Query problems ("too long", "too short") also
                # arrive as plain text with HTTP 200.
                try:
                    return json.loads(body).get("articles", [])
                except ValueError:
                    raise GdeltRejected(
                        " ".join(body.split())[:200]
                    ) from None

        raise GdeltRateLimited(
            f"GDELT still rate limited after {MAX_ATTEMPTS} attempts."
        )

    def _wait_for_slot(self) -> None:
        if self._last_request is not None:
            remaining = self._min_interval - (
                self._clock() - self._last_request
            )

            if remaining > 0:
                self._sleep(remaining)

        self._last_request = self._clock()


class GdeltDownloader:
    """
    Fills the archive (`make news`) and is also a live source
    of the desk. Live, it is refreshed rarely: the client
    allows one request every 5.5 seconds process-wide, and
    GDELT's index trails the present by days, so asking often
    would queue the other tickers for nothing new.
    """

    name = "gdelt"
    local = False
    min_refresh_minutes = 360

    def __init__(self, client: GdeltClient | None = None):
        self._client = client or GdeltClient()

    def signature(self, ticker: str, company: str) -> str:
        return sha1(build_query(ticker, company).encode()).hexdigest()[:8]

    def fetch(self, ticker, company, *, start, end) -> list[NewsItem]:
        articles = self._client.search(
            build_query(ticker, company), start=start, end=end
        )

        return [
            NewsItem(
                news_id="NEWS-" + sha1(row["url"].encode()).hexdigest()[:12],
                ticker=ticker,
                title=" ".join(row["title"].split()),
                url=row["url"],
                publisher=row.get("domain"),
                # seendate is when GDELT first crawled the page,
                # at 15-minute resolution. It can only be LATER
                # than publication, so using it as the
                # publication time may wrongly exclude evidence
                # but can never admit hindsight.
                published_at=datetime.strptime(
                    row["seendate"], "%Y%m%dT%H%M%SZ"
                ).replace(tzinfo=timezone.utc),
                provider=self.name,
            )
            for row in articles
            if row.get("url")
            and row.get("title")
            and row.get("seendate")
            # The query excludes as many farms as fit its
            # length budget; this catches the rest.
            and row.get("domain") not in CONTENT_FARMS
        ]
