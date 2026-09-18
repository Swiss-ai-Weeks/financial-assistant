from __future__ import annotations

from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)

import pandas as pd
import yfinance as yf

from .models import (
    MarketDataManifest,
)


def _normalise_download(
    raw: pd.DataFrame,
    tickers: tuple[str, ...],
) -> pd.DataFrame:
    """
    Convert yfinance's wide/MultiIndex result into the
    canonical ClaimGraph market-data shape:

        date | ticker | open | high | low | close | volume

    The anomaly detector already consumes this
    long-form representation.
    """

    if raw.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "ticker",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    rows = []

    for ticker in tickers:
        if isinstance(
            raw.columns,
            pd.MultiIndex,
        ):
            level_0 = set(
                raw.columns.get_level_values(
                    0
                )
            )

            level_1 = set(
                raw.columns.get_level_values(
                    1
                )
            )

            if ticker in level_0:
                block = raw[ticker].copy()

            elif ticker in level_1:
                block = raw.xs(
                    ticker,
                    axis=1,
                    level=1,
                ).copy()

            else:
                continue

        else:
            # Primarily useful for defensive handling
            # of a one-ticker response.
            if len(tickers) != 1:
                continue

            block = raw.copy()

        block = block.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )

        required = {
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        if not required.issubset(
            block.columns
        ):
            continue

        block = block[
            [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ].copy()

        block["date"] = (
            pd.to_datetime(
                block.index
            )
            .tz_localize(None)
            .normalize()
        )

        block["ticker"] = ticker

        rows.append(
            block.reset_index(
                drop=True
            )
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "ticker",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    frame = pd.concat(
        rows,
        ignore_index=True,
    )

    frame = frame.dropna(
        subset=["close"]
    )

    return (
        frame[
            [
                "date",
                "ticker",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ]
        .sort_values(
            [
                "date",
                "ticker",
            ]
        )
        .reset_index(
            drop=True
        )
    )


def download_daily_prices(
    tickers: tuple[str, ...],
    *,
    start: str | date,
    end: str | date,
) -> tuple[
    pd.DataFrame,
    MarketDataManifest,
]:
    """
    Download adjusted daily OHLCV observations.

    The public API treats `end` as inclusive even
    though yfinance's underlying `end` argument is
    exclusive.
    """

    clean_tickers = tuple(
        dict.fromkeys(
            ticker
            .strip()
            .upper()
            for ticker in tickers
            if ticker.strip()
        )
    )

    if not clean_tickers:
        raise ValueError(
            "At least one ticker is required."
        )

    start_date = pd.Timestamp(
        start
    ).date()

    end_date = pd.Timestamp(
        end
    ).date()

    if end_date < start_date:
        raise ValueError(
            "end must be on or after start."
        )

    # yfinance end is exclusive.
    exclusive_end = (
        end_date
        + timedelta(days=1)
    )

    raw = yf.download(
        tickers=list(
            clean_tickers
        ),

        start=(
            start_date.isoformat()
        ),

        end=(
            exclusive_end.isoformat()
        ),

        interval="1d",

        group_by="ticker",

        auto_adjust=True,

        actions=False,

        threads=True,

        progress=False,

        multi_level_index=True,
    )

    frame = _normalise_download(
        raw,
        clean_tickers,
    )

    manifest = MarketDataManifest(
        provider=(
            "Yahoo Finance via yfinance"
        ),

        interval="1d",

        requested_start=(
            start_date
        ),

        requested_end=(
            end_date
        ),

        retrieved_at=datetime.now(
            timezone.utc
        ),

        tickers=clean_tickers,

        auto_adjust=True,

        row_count=len(frame),
    )

    return (
        frame,
        manifest,
    )
