from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Protocol

import yfinance as yf

from financial_assistant.api.models import NewsItem
from financial_assistant.retrieval import SearchProvider


class NewsSource(Protocol):
    """
    `start` and `end` describe the period the desk is
    looking at. Sources that can only return "the latest"
    ignore them.

    A `local` source reads files that are already on disk.
    It is consulted on every request and its items are not
    copied into the accumulating cache.
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
    ) -> tuple[NewsItem, ...]:
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


class NewsRepository:
    """
    Ticker news merged across sources and accumulated
    on disk.

    Remote sources only expose a rolling window, so every
    refresh is merged into what was already seen and the
    cache grows for as long as the desk runs.

    Local sources (a downloaded archive) are merged in at
    read time.
    """

    def __init__(
        self,
        cache_dir: Path,
        sources: tuple[NewsSource, ...],
        *,
        cache_minutes: int,
    ):
        self._cache_dir = cache_dir
        self._sources = sources
        self._cache_seconds = cache_minutes * 60
        self._lock = threading.Lock()

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
    ) -> tuple[NewsItem, ...]:
        symbol = ticker.strip().upper()
        remote = [source for source in self._sources if not source.local]

        with self._lock:
            path = self._cache_dir / f"{symbol}.json"
            known = self._read(path)

            fresh = (
                path.is_file()
                and time.time() - path.stat().st_mtime < self._cache_seconds
            )

            if not fresh:
                for source in remote:
                    try:
                        fetched = source.fetch(
                            symbol, company, start=start, end=end
                        )
                    except Exception:
                        # One dead source must not blank
                        # the feed.
                        continue

                    for item in fetched:
                        known.setdefault(item.news_id, item)

                self._write(path, known)

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
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        path.write_text(
            json.dumps(
                [item.model_dump(mode="json") for item in items.values()],
                indent=1,
            )
        )

