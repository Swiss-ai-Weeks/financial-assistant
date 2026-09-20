"""
News downloaded once and replayed from disk.

    NewsDownloader      one per provider: fetches a slice of history
    NewsArchive         local store: download into it, read from it
    ArchiveNewsSource   NewsSource that ONLY reads the archive

Splitting download from serving is deliberate. Historical news
APIs are rate limited (GDELT: one request every five seconds)
and cannot sit behind an interactive desk. Downloading ahead of
time also makes a recorded demo reproducible: the desk "fetches"
news exactly as it would live, from files that no longer change.

Providers are interchangeable. Whatever can return articles for
a company between two dates can fill the archive.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from financial_assistant.api.models import NewsItem


SLICE_DAYS = 7


class NewsDownloader(Protocol):
    name: str

    # Identifies HOW the provider is queried. Changing the
    # query invalidates the slices recorded under the old one.
    def signature(self, ticker: str, company: str) -> str:
        ...

    def fetch(
        self,
        ticker: str,
        company: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[NewsItem]:
        ...


def slices(start: datetime, end: datetime):
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


class NewsArchive:
    """
        <dir>/<TICKER>.jsonl   one article per line
        <dir>/manifest.json    which slices are complete, per provider

    Only titles, summaries, URLs and timestamps are stored,
    never article text, so the archive stays small and can be
    committed alongside the demo.
    """

    def __init__(self, directory: Path):
        self._directory = directory
        self._lock = threading.Lock()

    def download(
        self,
        downloader: NewsDownloader,
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
        now = now or datetime.now(timezone.utc)
        signature = downloader.signature(symbol, company)

        manifest = self._read_manifest()
        added = 0

        for slice_start, slice_end in slices(start, end):
            if slice_start > now:
                break

            key = (
                f"{downloader.name}:{symbol}:"
                f"{slice_start:%Y-%m-%d}:{signature}"
            )

            if key in manifest:
                continue

            items = downloader.fetch(
                symbol,
                company,
                start=slice_start,
                end=min(slice_end, now),
            )

            new = self._append(symbol, items)
            added += new

            if slice_end < now:
                manifest[key] = {
                    "articles": len(items),
                    "downloaded_at": now.isoformat(),
                }

                self._write_manifest(manifest)

            if on_progress:
                on_progress(
                    f"{downloader.name} {symbol} {slice_start:%Y-%m-%d}: "
                    f"{len(items)} articles, {new} new"
                )

        return added

    def read(
        self,
        ticker: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[NewsItem, ...]:
        path = self._path(ticker.strip().upper())

        if not path.is_file():
            return ()

        items = (
            NewsItem.model_validate_json(line)
            for line in path.read_text().splitlines()
        )

        return tuple(
            item
            for item in items
            if (start is None or item.published_at >= start)
            and (end is None or item.published_at <= end)
        )

    # -------------------------------------------------

    def _append(self, symbol: str, items: list[NewsItem]) -> int:
        with self._lock:
            path = self._path(symbol)

            known = (
                {
                    json.loads(line)["news_id"]
                    for line in path.read_text().splitlines()
                }
                if path.is_file()
                else set()
            )

            fresh = {
                item.news_id: item
                for item in items
                if item.news_id not in known
            }

            if fresh:
                self._directory.mkdir(parents=True, exist_ok=True)

                with path.open("a") as handle:
                    for item in fresh.values():
                        handle.write(item.model_dump_json() + "\n")

            return len(fresh)

    def _path(self, symbol: str) -> Path:
        return self._directory / f"{symbol.replace('/', '_')}.jsonl"

    def _read_manifest(self) -> dict:
        path = self._directory / "manifest.json"

        return json.loads(path.read_text()) if path.is_file() else {}

    def _write_manifest(self, manifest: dict) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        (self._directory / "manifest.json").write_text(
            json.dumps(manifest, indent=1, sort_keys=True) + "\n"
        )


class ArchiveNewsSource:
    """
    Serves news from the local archive.

    It never touches the network: whatever was downloaded
    is what the desk can see, which is what makes a replay
    reproducible.
    """

    name = "archive"
    local = True

    def __init__(self, archive: NewsArchive):
        self._archive = archive

    def fetch(self, ticker, company, *, start=None, end=None):
        return self._archive.read(ticker, start=start, end=end)
