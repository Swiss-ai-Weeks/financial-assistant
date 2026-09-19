from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from financial_assistant.api.errors import NotFound, UpstreamUnavailable
from financial_assistant.market_data import download_daily_prices


COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]


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
        downloader=download_daily_prices,
    ):
        self._cache_dir = cache_dir
        self._history_days = history_days
        self._cache_seconds = cache_minutes * 60
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

        return pd.concat(frames, ignore_index=True)

    def get_available(self, tickers: tuple[str, ...]) -> pd.DataFrame:
        """
        Like get_prices, but silently drops tickers with
        no history. Used for peer universes, where one
        delisted symbol must not break the scan.
        """

        wanted = tuple(dict.fromkeys(t.strip().upper() for t in tickers))

        with self._lock:
            stale = [t for t in wanted if self._load(t) is None]

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

        return pd.concat(frames, ignore_index=True)

    # -------------------------------------------------

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
