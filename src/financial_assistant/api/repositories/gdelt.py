"""
GDELT news, downloaded once and replayed from disk.

    GdeltClient        talks to the GDELT DOC 2.0 API
    GdeltArchive       local archive: download into it, read from it
    GdeltNewsSource    NewsSource that ONLY reads the archive

Splitting download from serving is deliberate. GDELT allows
one request every five seconds, so it cannot sit behind an
interactive desk. Downloading ahead of time also makes a
recorded demo reproducible: the desk "fetches" news exactly
as it would live, but from files that no longer change.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from financial_assistant.api.models import NewsItem
from financial_assistant.api.relevance import company_phrase


ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT returns at most 250 articles per request. A busy
# name exceeds that within days, so a window is downloaded
# in slices and each slice keeps its most relevant articles.
MAX_RECORDS = 250
SLICE_DAYS = 7

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


def _slices(start: datetime, end: datetime):
    """
    Calendar-aligned slices covering [start, end].

    Aligning to fixed boundaries, instead of counting from
    `start`, means two overlapping windows share slices and
    nothing is downloaded twice.
    """

    epoch = datetime(2017, 1, 1, tzinfo=timezone.utc)
    step = timedelta(days=SLICE_DAYS)

    cursor = epoch + step * ((start - epoch) // step)

    while cursor <= end:
        yield cursor, cursor + step - timedelta(seconds=1)
        cursor += step


def _parse_seen(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
        tzinfo=timezone.utc
    )


class GdeltArchive:
    """
    Local archive of GDELT article metadata.

        <dir>/<TICKER>.jsonl   one article per line
        <dir>/manifest.json    which slices are complete

    Only titles, URLs and timestamps are stored, never
    article text, so the archive is small and can be
    committed alongside the demo.
    """

    def __init__(self, directory: Path, client: GdeltClient | None = None):
        self._directory = directory
        self._client = client or GdeltClient()
        self._lock = threading.Lock()

    # -------------------------------------------------
    # Download
    # -------------------------------------------------

    def download(
        self,
        ticker: str,
        company: str,
        *,
        start: datetime,
        end: datetime,
        now: datetime | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> int:
        """
        Download every missing slice of the window and
        return how many new articles were archived.

        Resumable: finished slices are recorded, so an
        interrupted or rate-limited run continues where it
        stopped. A slice that is still open (it ends in the
        future) is downloaded but not recorded as finished.
        """

        symbol = ticker.strip().upper()
        query = build_query(symbol, company)
        now = now or datetime.now(timezone.utc)

        manifest = self._read_manifest()
        added = 0

        for slice_start, slice_end in _slices(start, end):
            if slice_start > now:
                break

            key = self._slice_key(symbol, query, slice_start)

            if key in manifest:
                continue

            articles = self._client.search(
                query,
                start=slice_start,
                end=min(slice_end, now),
            )

            new = self._append(symbol, articles)
            added += new

            if slice_end < now:
                manifest[key] = {
                    "articles": len(articles),
                    "downloaded_at": now.isoformat(),
                }

                self._write_manifest(manifest)

            if on_progress:
                on_progress(
                    f"{symbol} {slice_start:%Y-%m-%d}: "
                    f"{len(articles)} articles, {new} new"
                )

        return added

    # -------------------------------------------------
    # Read
    # -------------------------------------------------

    def read(
        self,
        ticker: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[NewsItem, ...]:
        symbol = ticker.strip().upper()
        path = self._articles_path(symbol)

        if not path.is_file():
            return ()

        items = []

        for line in path.read_text().splitlines():
            row = json.loads(line)
            seen = _parse_seen(row["seendate"])

            if (start and seen < start) or (end and seen > end):
                continue

            if row.get("domain") in CONTENT_FARMS:
                continue

            items.append(
                NewsItem(
                    news_id="NEWS-" + sha1(row["url"].encode()).hexdigest()[:12],
                    ticker=symbol,
                    title=" ".join(row["title"].split()),
                    url=row["url"],
                    publisher=row.get("domain"),
                    # seendate is when GDELT first crawled the
                    # page, at 15-minute resolution. It can only
                    # be LATER than publication, so using it as
                    # the publication time may wrongly exclude
                    # evidence but can never admit hindsight.
                    published_at=seen,
                    provider=GdeltNewsSource.name,
                )
            )

        return tuple(items)

    def covered_tickers(self) -> tuple[str, ...]:
        if not self._directory.is_dir():
            return ()

        return tuple(sorted(p.stem for p in self._directory.glob("*.jsonl")))

    # -------------------------------------------------

    def _append(self, symbol: str, articles: list[dict]) -> int:
        with self._lock:
            path = self._articles_path(symbol)

            known = set()

            if path.is_file():
                known = {
                    json.loads(line)["url"]
                    for line in path.read_text().splitlines()
                }

            fresh = [
                article
                for article in articles
                if article.get("url")
                and article.get("title")
                and article.get("seendate")
                and article["url"] not in known
            ]

            if fresh:
                self._directory.mkdir(parents=True, exist_ok=True)

                with path.open("a") as handle:
                    for article in fresh:
                        handle.write(
                            json.dumps(
                                {
                                    key: article.get(key)
                                    for key in (
                                        "url",
                                        "title",
                                        "seendate",
                                        "domain",
                                        "sourcecountry",
                                    )
                                }
                            )
                            + "\n"
                        )

            return len(fresh)

    @staticmethod
    def _slice_key(symbol: str, query: str, slice_start: datetime) -> str:
        digest = sha1(query.encode("utf-8")).hexdigest()[:8]

        return f"{symbol}:{slice_start:%Y-%m-%d}:{digest}"

    def _articles_path(self, symbol: str) -> Path:
        return self._directory / f"{symbol.replace('/', '_')}.jsonl"

    def _read_manifest(self) -> dict:
        path = self._directory / "manifest.json"

        return json.loads(path.read_text()) if path.is_file() else {}

    def _write_manifest(self, manifest: dict) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        (self._directory / "manifest.json").write_text(
            json.dumps(manifest, indent=1, sort_keys=True) + "\n"
        )


class GdeltNewsSource:
    """
    Serves GDELT news from the local archive.

    It never touches the network: whatever was downloaded
    is what the desk can see, which is what makes a replay
    reproducible.
    """

    name = "gdelt"
    local = True

    def __init__(self, archive: GdeltArchive):
        self._archive = archive

    def fetch(
        self,
        ticker: str,
        company: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[NewsItem, ...]:
        return self._archive.read(ticker, start=start, end=end)
