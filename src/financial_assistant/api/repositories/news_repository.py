"""
The news wire of the desk.

    NewsSource                 what a provider has to offer
    YahooNewsSource            keyless, the latest weeks
    SearchProviderNewsSource   any retrieval SearchProvider
    NewsRepository             all of them, cached on disk

The keyed providers (Finnhub, Alpha Vantage, EODHD, GNews,
Marketaux, NewsAPI) live in modules of their own and satisfy
the same NewsSource protocol.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from typing import Protocol

import yfinance as yf

from financial_assistant.api.models import NewsItem
from financial_assistant.retrieval import SearchProvider

from .news_provider import NewsProviderRateLimited, scrub


META_FILE = "_meta.json"

# A provider that says its quota is spent is left alone for
# this long, whatever its budget says.
RATE_LIMIT_BACKOFF_MINUTES = 60

FETCH_WORKERS = 8
REFRESH_WORKERS = 2


class NewsSource(Protocol):
    """
    `start` and `end` describe the period the desk is
    looking at. Sources that can only return "the latest"
    ignore them.

    A `local` source reads files that are already on disk.
    It is consulted on every request and its items are not
    copied into the accumulating cache.

    A remote source may also declare `min_refresh_minutes`
    (how often one ticker is worth asking about) and
    `daily_budget` (requests a day, across tickers). The
    repository enforces both. Without them a source is
    refreshed at the repository's own pace, unbudgeted.
    """

    name: str
    local: bool

    def fetch(
        self,
        ticker: str,
        company: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Sequence[NewsItem]:
        ...


def _news_id(url: str) -> str:
    return "NEWS-" + sha1(url.encode("utf-8")).hexdigest()[:12]


class YahooNewsSource:
    """
    Keyless ticker news from Yahoo Finance.

    Returns roughly the latest month of coverage with
    full publication timestamps, which is what makes it
    usable for point-in-time evidence.
    """

    name = "yahoo-finance"
    local = False

    def __init__(self, count: int = 200):
        self._count = count

    def fetch(self, ticker, company, *, start=None, end=None):
        raw = yf.Ticker(ticker).get_news(count=self._count, tab="news")
        items = []

        for entry in raw:
            content = entry.get("content") or {}

            url = (
                (content.get("canonicalUrl") or {}).get("url")
                or (content.get("clickThroughUrl") or {}).get("url")
            )

            title = content.get("title")
            published = content.get("pubDate")

            if not url or not title or not published:
                continue

            items.append(
                NewsItem(
                    news_id=_news_id(url),
                    ticker=ticker,
                    title=title.strip(),
                    url=url,
                    publisher=(content.get("provider") or {}).get(
                        "displayName"
                    ),
                    published_at=datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    ),
                    summary=(content.get("summary") or "").strip(),
                    provider=self.name,
                )
            )

        return tuple(items)


class SearchProviderNewsSource:
    """
    Adapts any retrieval SearchProvider (SearXNG,
    NewsAPI) into a ticker news source.

    Hits without a full publication timestamp are
    dropped: an undated headline cannot be placed on
    the timeline, so it cannot explain anything.
    """

    def __init__(self, provider: SearchProvider, *, limit: int = 25):
        self._provider = provider
        self._limit = limit
        self.name = provider.name
        self.local = False

    def fetch(self, ticker, company, *, start=None, end=None):
        subject = company if company and company != ticker else ticker

        hits = self._provider.search(
            f"{subject} {ticker} stock news",
            task_id=f"NEWS-{ticker}",
            limit=self._limit,
        )

        return tuple(
            NewsItem(
                news_id=_news_id(str(hit.url)),
                ticker=ticker,
                title=hit.title,
                url=str(hit.url),
                publisher=hit.publisher,
                published_at=hit.published_at,
                summary=hit.snippet,
                provider=self.name,
            )
            for hit in hits
            if hit.published_at is not None and not hit.published_date_only
        )


@dataclass(frozen=True)
class NewsSourceStatus:
    """
    What the desk can say about one source without asking
    it anything. Never holds a URL: URLs hold keys.
    """

    name: str
    configured: bool
    local: bool = False
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    requests_today: int = 0
    daily_budget: int | None = None
    min_refresh_minutes: int | None = None
    articles: int = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NewsRepository:
    """
    Ticker news merged across sources and accumulated
    on disk.

        <dir>/<TICKER>.json   every article seen so far
        <dir>/_meta.json      per source: when asked, how often today

    Remote sources only expose a rolling window, so every
    refresh is merged into what was already seen and the
    cache grows for as long as the desk runs.

    The desk never waits for eight providers. A ticker that
    has anything cached is answered from the cache at once
    and refreshed behind the request (stale-while-revalidate).
    Only a ticker seen for the first time waits for its
    first fetch.

    Free tiers are counted in requests per DAY, so each
    source is asked about a ticker at most every
    `min_refresh_minutes` and at most `daily_budget` times a
    day in total. Both are recorded on disk: restarting the
    desk ten times must not spend ten times the quota.

    Local sources (a downloaded archive) are merged in at
    read time.
    """

    def __init__(
        self,
        cache_dir: Path,
        sources: tuple[NewsSource, ...],
        *,
        cache_minutes: int,
        background: bool = True,
        unconfigured: tuple[str, ...] = (),
        now: Callable[[], datetime] = _utc_now,
    ):
        self._cache_dir = cache_dir
        self._sources = sources

        # The pace of a source that declares none of its own.
        self._cache_minutes = cache_minutes

        # False runs every refresh inside get(): scripts that
        # exit right after, and tests.
        self._background = background

        # Providers the desk knows but has no key for. Only
        # reported, so the UI can say what is missing.
        self._unconfigured = unconfigured
        self._now = now

        self._state_lock = threading.Lock()
        self._ticker_locks: dict[str, threading.Lock] = {}
        self._refreshing: set[str] = set()

        self._meta_lock = threading.Lock()
        self._meta: dict | None = None

        self._fetch_pool: ThreadPoolExecutor | None = None
        self._refresh_pool: ThreadPoolExecutor | None = None

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(source.name for source in self._sources)

    def get(
        self,
        ticker: str,
        company: str = "",
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        force: bool = False,
        slice: str | None = None,
    ) -> tuple[NewsItem, ...]:
        """
        `force` asks every remote source again, now, and
        waits for the answers. It overrides the refresh
        interval but not the daily budget: a quota that is
        spent stays spent however hard the button is pressed.

        `slice` names a period of the past (a week the
        manager clicked on the chart). The sources are asked
        for that window, paced and budgeted apart from the
        rolling feed, and the request waits for the answers:
        the cache has nothing for a period nobody asked
        about before, so there is nothing to serve meanwhile.
        """

        symbol = ticker.strip().upper()
        known = self._read(self._path(symbol))

        subject = symbol if slice is None else f"{symbol}@{slice}"

        if force or self._due(subject, force=False):
            if known and self._background and not force and slice is None:
                self._refresh_later(symbol, company, start, end)
            else:
                known = self._refresh(symbol, company, start, end, force, subject)

        for source in self._sources:
            if source.local:
                for item in source.fetch(symbol, company, start=start, end=end):
                    known.setdefault(item.news_id, item)

        return tuple(
            sorted(
                known.values(),
                key=lambda item: item.published_at,
                reverse=True,
            )
        )

    def status(self) -> tuple[NewsSourceStatus, ...]:
        today = self._now().date().isoformat()

        def moment(value: str | None) -> datetime | None:
            return datetime.fromisoformat(value) if value else None

        with self._meta_lock:
            recorded = self._load_meta()["sources"]

            rows = []

            for source in self._sources:
                entry = recorded.get(source.name, {})

                rows.append(
                    NewsSourceStatus(
                        name=source.name,
                        configured=True,
                        local=source.local,
                        last_attempt=moment(entry.get("last_attempt")),
                        last_success=moment(entry.get("last_success")),
                        last_error=entry.get("last_error"),
                        requests_today=(
                            entry.get("requests_today", 0)
                            if entry.get("day") == today
                            else 0
                        ),
                        daily_budget=getattr(source, "daily_budget", None),
                        min_refresh_minutes=(
                            None
                            if source.local
                            else self._refresh_minutes(source)
                        ),
                        articles=entry.get("articles", 0),
                    )
                )

        rows += [
            NewsSourceStatus(name=name, configured=False)
            for name in self._unconfigured
        ]

        return tuple(rows)

    # -------------------------------------------------
    # Refreshing
    # -------------------------------------------------

    def _refresh_later(self, symbol, company, start, end) -> None:
        """
        At most one refresh per ticker is ever queued: a
        page that asks for the same ticker five times while
        the first refresh runs starts nothing new.
        """

        with self._state_lock:
            if symbol in self._refreshing:
                return

            self._refreshing.add(symbol)

            if self._refresh_pool is None:
                self._refresh_pool = ThreadPoolExecutor(
                    max_workers=REFRESH_WORKERS,
                    thread_name_prefix="news-refresh",
                )

        def run():
            try:
                self._refresh(symbol, company, start, end, False)
            except Exception:
                # Nobody is waiting for this. The cache
                # simply stays as it was.
                pass
            finally:
                with self._state_lock:
                    self._refreshing.discard(symbol)

        try:
            self._refresh_pool.submit(run)
        except RuntimeError:
            # Interpreter shutting down.
            with self._state_lock:
                self._refreshing.discard(symbol)

    def _refresh(
        self, symbol, company, start, end, force, subject=None
    ) -> dict[str, NewsItem]:
        # One refresh per ticker at a time. Whoever waited
        # here finds nothing due any more and reads what the
        # first one wrote.
        with self._ticker_lock(symbol):
            sources = self._reserve(subject or symbol, force=force)

            if not sources:
                return self._read(self._path(symbol))

            # A request for a period of the past waits for
            # its answers, but not for a source that declares
            # itself slow (GDELT: seconds per request, and a
            # queue behind the book's own refresh). That one
            # fills in behind the request.
            deferred = [
                source
                for source in sources
                if subject != symbol and not force and getattr(source, "slow", False)
            ]

            known = self._collect(
                symbol, company, start, end,
                [source for source in sources if source not in deferred],
            )

        if deferred:
            self._collect_later(symbol, company, start, end, deferred)

        return known

    def _collect(self, symbol, company, start, end, sources) -> dict[str, NewsItem]:
        """Ask `sources`, merge what they return into the ticker's file."""

        path = self._path(symbol)

        if not sources:
            return self._read(path)

        def fetch(source):
            try:
                return list(
                    source.fetch(symbol, company, start=start, end=end)
                )
            except Exception as error:
                # One dead source must not blank the feed.
                return error

        if len(sources) == 1:
            results = [fetch(sources[0])]
        else:
            results = list(self._fetchers().map(fetch, sources))

        known = self._read(path)
        outcomes = []

        # Merged in source order, not in order of arrival,
        # so which copy of a story is kept does not depend
        # on which provider was quicker today.
        for source, result in zip(sources, results):
            if isinstance(result, Exception):
                outcomes.append((source, result, 0))
                continue

            new = 0

            for item in result:
                if item.news_id not in known:
                    known[item.news_id] = item
                    new += 1

            outcomes.append((source, None, new))

        self._write(path, known)
        self._record(outcomes)

        return known

    def _collect_later(self, symbol, company, start, end, sources) -> None:
        with self._state_lock:
            if self._refresh_pool is None:
                self._refresh_pool = ThreadPoolExecutor(
                    max_workers=REFRESH_WORKERS,
                    thread_name_prefix="news-refresh",
                )

        def run():
            try:
                with self._ticker_lock(symbol):
                    self._collect(symbol, company, start, end, sources)
            except Exception:
                # Nobody is waiting for this.
                pass

        self._refresh_pool.submit(run)

    def _due(self, symbol: str, *, force: bool) -> list[NewsSource]:
        now = self._now()

        with self._meta_lock:
            meta = self._load_meta()

            return [
                source
                for source in self._sources
                if not source.local
                and self._is_due(meta, source, symbol, now, force)
            ]

    def _reserve(self, symbol: str, *, force: bool) -> list[NewsSource]:
        """
        Decide who is asked and charge the request BEFORE it
        is made. Charged afterwards, a desk that is killed
        mid-request, or eight tickers refreshing at once,
        would overspend the budget.
        """

        now = self._now()

        with self._meta_lock:
            meta = self._load_meta()

            due = [
                source
                for source in self._sources
                if not source.local
                and self._is_due(meta, source, symbol, now, force)
            ]

            for source in due:
                entry = self._entry(meta, source.name, now)

                entry["requests_today"] += 1
                entry["last_attempt"] = now.isoformat()
                entry["tickers"][symbol] = now.isoformat()

            if due:
                self._save_meta()

        return due

    def _record(self, outcomes) -> None:
        now = self._now()

        with self._meta_lock:
            meta = self._load_meta()

            for source, error, new in outcomes:
                entry = self._entry(meta, source.name, now)

                if error is None:
                    entry["last_success"] = now.isoformat()
                    entry["last_error"] = None
                    entry["articles"] += new
                    continue

                # Providers scrub their own errors. Anything
                # else (requests, urllib) may quote the URL
                # it failed on, key included.
                entry["last_error"] = (
                    scrub(str(error)) or type(error).__name__
                )

                if isinstance(error, NewsProviderRateLimited):
                    entry["blocked_until"] = (
                        now + timedelta(minutes=RATE_LIMIT_BACKOFF_MINUTES)
                    ).isoformat()

            self._save_meta()

    def _is_due(self, meta, source, symbol, now, force) -> bool:
        entry = meta["sources"].get(source.name, {})
        today = now.date().isoformat()

        blocked_until = entry.get("blocked_until")

        if blocked_until and now < datetime.fromisoformat(blocked_until):
            return False

        budget = getattr(source, "daily_budget", None)
        spent = entry.get("requests_today", 0) if entry.get("day") == today else 0

        if budget is not None and spent >= budget:
            return False

        if force:
            return True

        asked = entry.get("tickers", {}).get(symbol)

        return asked is None or now - datetime.fromisoformat(
            asked
        ) >= timedelta(minutes=self._refresh_minutes(source))

    def _refresh_minutes(self, source) -> int:
        declared = getattr(source, "min_refresh_minutes", None)

        return self._cache_minutes if declared is None else declared

    @staticmethod
    def _entry(meta: dict, name: str, now: datetime) -> dict:
        entry = meta["sources"].setdefault(name, {})
        today = now.date().isoformat()

        # Quotas reset at midnight UTC, close enough to every
        # provider's own reset.
        if entry.get("day") != today:
            entry["day"] = today
            entry["requests_today"] = 0

        entry.setdefault("articles", 0)
        entry.setdefault("tickers", {})

        return entry

    # -------------------------------------------------
    # Plumbing
    # -------------------------------------------------

    def _ticker_lock(self, symbol: str) -> threading.Lock:
        with self._state_lock:
            return self._ticker_locks.setdefault(symbol, threading.Lock())

    def _fetchers(self) -> ThreadPoolExecutor:
        # Separate from the refresh pool on purpose: a refresh
        # waits for its fetches, and a pool whose workers wait
        # for work queued on the same pool never finishes.
        with self._state_lock:
            if self._fetch_pool is None:
                self._fetch_pool = ThreadPoolExecutor(
                    max_workers=FETCH_WORKERS,
                    thread_name_prefix="news-fetch",
                )

            return self._fetch_pool

    def _path(self, symbol: str) -> Path:
        return self._cache_dir / f"{symbol.replace('/', '_')}.json"

    def _load_meta(self) -> dict:
        if self._meta is None:
            path = self._cache_dir / META_FILE

            try:
                meta = json.loads(path.read_text()) if path.is_file() else {}
            except ValueError:
                meta = {}

            if not isinstance(meta.get("sources"), dict):
                meta = {"sources": {}}

            self._meta = meta

        return self._meta

    def _save_meta(self) -> None:
        self._write_json(self._cache_dir / META_FILE, self._meta)

    @staticmethod
    def _read(path: Path) -> dict[str, NewsItem]:
        if not path.is_file():
            return {}

        try:
            rows = json.loads(path.read_text())
        except ValueError:
            return {}

        items = (NewsItem.model_validate(row) for row in rows)

        return {item.news_id: item for item in items}

    def _write(self, path: Path, items: dict[str, NewsItem]) -> None:
        self._write_json(
            path,
            [item.model_dump(mode="json") for item in items.values()],
        )

    def _write_json(self, path: Path, payload) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Written aside and moved into place: a request that
        # reads the cache while a refresh writes it must see
        # the old file or the new one, never half of either.
        draft = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
        draft.write_text(json.dumps(payload, indent=1))
        os.replace(draft, path)
