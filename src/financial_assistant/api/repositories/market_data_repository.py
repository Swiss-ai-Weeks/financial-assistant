from __future__ import annotations

import json
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from financial_assistant.api.clock import DeskClock, as_clock
from financial_assistant.api.errors import NotFound, UpstreamUnavailable
from financial_assistant.market_data import download_daily_prices


COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]

# Filling a large universe (see MarketDataRepository.download).
RETRY_CHUNK = 10
UNKNOWN_SHARE = 0.2
UNKNOWN_DAYS = 7


class MarketDataRepository:
    """
    Daily OHLCV history, one cached CSV per ticker.

    The canonical long shape used by the detectors is
    preserved:

        date | ticker | open | high | low | close | volume
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        history_days: int,
        cache_minutes: int,
        as_of: date | DeskClock | None = None,
        downloader=download_daily_prices,
    ):
        self._cache_dir = cache_dir
        self._history_days = history_days
        self._cache_seconds = cache_minutes * 60
        self._clock = as_clock(as_of)
        self._download = downloader

        self._lock = threading.Lock()
        self._memory: dict[str, tuple[float, pd.DataFrame]] = {}

    def get_prices(self, tickers: tuple[str, ...]) -> pd.DataFrame:
        """
        Long-form history for every requested ticker.

        Raises NotFound when a ticker has no history at
        all, which is how an unknown symbol shows up.
        """

        wanted = tuple(dict.fromkeys(t.strip().upper() for t in tickers))

        with self._lock:
            stale = [t for t in wanted if self._load(t) is None]

            if stale:
                self._refresh(tuple(stale))

            frames = []

            for ticker in wanted:
                frame = self._load(ticker, allow_stale=True)

                if frame is None or frame.empty:
                    raise NotFound(
                        f"No market history found for {ticker}."
                    )

                frames.append(frame)

        return self._visible(pd.concat(frames, ignore_index=True))

    def get_available(
        self,
        tickers: tuple[str, ...],
        *,
        refresh: tuple[str, ...] | None = None,
    ) -> pd.DataFrame:
        """
        Like get_prices, but silently drops tickers with
        no history. Used for peer universes, where one
        delisted symbol must not break the scan.

        `refresh` names the only tickers worth a download. A
        universe of thousands is filled ahead of time (`make
        universe`) and read from disk as it is: an interactive
        request must never start a 3,000-ticker download.
        """

        wanted = tuple(dict.fromkeys(t.strip().upper() for t in tickers))

        allowed = (
            None
            if refresh is None
            else {t.strip().upper() for t in refresh}
        )

        with self._lock:
            stale = [
                t
                for t in wanted
                if (allowed is None or t in allowed)
                and self._load(t) is None
            ]

            if stale:
                try:
                    self._refresh(tuple(stale))
                except UpstreamUnavailable:
                    pass

            frames = [
                frame
                for ticker in wanted
                if (frame := self._load(ticker, allow_stale=True)) is not None
                and not frame.empty
            ]

        if not frames:
            return pd.DataFrame(columns=COLUMNS)

        return self._visible(pd.concat(frames, ignore_index=True))

    # -------------------------------------------------

    def cached_tickers(self) -> frozenset[str]:
        """Tickers with history on disk, fresh or not."""

        if not self._cache_dir.is_dir():
            return frozenset()

        return frozenset(
            path.stem.upper() for path in self._cache_dir.glob("*.csv")
        )

    def download(
        self,
        tickers: tuple[str, ...],
        *,
        chunk: int = 100,
        on_progress=None,
    ) -> int:
        """
        Fill the cache for a large universe, a chunk at a time,
        skipping what is already fresh. Returns how many
        tickers now have history.

        Resumable and patient with Yahoo:
          - a chunk that fails outright is skipped, and the next
            run picks it up;
          - tickers a chunk came back without are asked for once
            more, in small groups: most such gaps are transient
            (a throttled request, a locked cache), not missing
            companies;
          - what Yahoo still does not know after that (delisted
            or renamed since the index snapshot) is remembered
            for a week, so every later run does not pay for it
            again.
        """

        wanted = tuple(dict.fromkeys(t.strip().upper() for t in tickers))
        unknown = self._read_unknown()

        with self._lock:
            stale = [
                t
                for t in wanted
                if t not in unknown and self._load(t) is None
            ]

        def report(line: str) -> None:
            if on_progress:
                on_progress(line)

        if unknown:
            report(f"{len(unknown)} tickers Yahoo did not know last time are skipped")

        for start in range(0, len(stale), chunk):
            batch = tuple(stale[start:start + chunk])

            if not self._try_refresh(batch, report):
                continue

            missing = [t for t in batch if not self._path(t).is_file()]

            for index in range(0, len(missing), RETRY_CHUNK):
                self._try_refresh(tuple(missing[index:index + RETRY_CHUNK]), report)

            still = [t for t in missing if not self._path(t).is_file()]

            # A few names missing is the index snapshot ageing. A
            # large share missing is Yahoo refusing us: nothing is
            # written off on a bad day.
            if still and len(still) <= len(batch) * UNKNOWN_SHARE:
                unknown.update(dict.fromkeys(still, time.time()))
                self._write_unknown(unknown)

            report(
                f"{min(start + chunk, len(stale))}/{len(stale)} requested"
                + (f", {len(still)} without history: {' '.join(still[:8])}" if still else "")
            )

        return len(self.cached_tickers() & set(wanted))

    def _try_refresh(self, batch: tuple[str, ...], report) -> bool:
        if not batch:
            return True

        try:
            with self._lock:
                self._refresh(batch)
        except UpstreamUnavailable as error:
            report(f"skipped {len(batch)} tickers: {error.message}")

            return False

        return True

    def _unknown_path(self) -> Path:
        return self._cache_dir / "_unknown.json"

    def _read_unknown(self) -> dict[str, float]:
        try:
            recorded = json.loads(self._unknown_path().read_text())
        except (OSError, ValueError):
            return {}

        horizon = time.time() - UNKNOWN_DAYS * 86400

        return {
            ticker: seen
            for ticker, seen in recorded.items()
            if isinstance(seen, (int, float)) and seen >= horizon
        }

    def _write_unknown(self, unknown: dict[str, float]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._unknown_path().write_text(json.dumps(unknown, indent=1, sort_keys=True))

    def _visible(self, frame: pd.DataFrame) -> pd.DataFrame:
        """
        Replay boundary. Every detector downstream is
        point-in-time relative to the latest session it is
        given, so hiding later sessions here is enough to
        replay the whole desk on a past date.
        """

        as_of = self._clock.as_of

        if as_of is None:
            return frame

        return frame.loc[frame["date"] <= pd.Timestamp(as_of)]

    def _path(self, ticker: str) -> Path:
        return self._cache_dir / f"{ticker.replace('/', '_')}.csv"

    def _load(
        self,
        ticker: str,
        *,
        allow_stale: bool = False,
    ) -> pd.DataFrame | None:
        cached = self._memory.get(ticker)

        if cached is not None:
            loaded_at, frame = cached

            if allow_stale or time.time() - loaded_at < self._cache_seconds:
                return frame

        path = self._path(ticker)

        if not path.is_file():
            return None

        modified_at = path.stat().st_mtime

        if not allow_stale and time.time() - modified_at >= self._cache_seconds:
            return None

        frame = pd.read_csv(path, parse_dates=["date"])
        self._memory[ticker] = (modified_at, frame)

        return frame

    def _refresh(self, tickers: tuple[str, ...]) -> None:
        end = date.today()
        start = end - timedelta(days=self._history_days)

        try:
            frame, _ = self._download(tickers, start=start, end=end)
        except Exception as exc:
            # Stale data is better than no desk at all.
            if all(self._path(t).is_file() for t in tickers):
                return

            raise UpstreamUnavailable(
                f"Market data download failed: {exc}"
            ) from exc

        self._cache_dir.mkdir(parents=True, exist_ok=True)

        for ticker in tickers:
            rows = frame.loc[frame["ticker"] == ticker, COLUMNS]

            if rows.empty:
                continue

            rows.to_csv(self._path(ticker), index=False)
            self._memory[ticker] = (time.time(), rows.reset_index(drop=True))
