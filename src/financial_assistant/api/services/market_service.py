from __future__ import annotations

from datetime import timedelta

import pandas as pd

from financial_assistant.anomaly_detection.signals import (
    moving_average,
    rolling_twap,
    rolling_vwap,
)
from financial_assistant.api.repositories import MarketDataRepository
from financial_assistant.api.schemas import (
    Candle,
    CandleSeries,
    Quote,
    ReviewWindow,
)


FAST_WINDOW = 7
SLOW_WINDOW = 25
VWAP_WINDOW = 20
TWAP_WINDOW = 5


def review_window(prices: pd.DataFrame, review_days: int) -> ReviewWindow:
    """
    The period under review ends on the latest session
    in the data, not on today's calendar date.
    """

    end = pd.to_datetime(prices["date"]).max().date()

    return ReviewWindow(
        start=end - timedelta(days=review_days),
        end=end,
        days=review_days,
    )


def return_since(closes: pd.Series, start) -> float:
    """
    Buy-and-hold return from the last close at or before
    `start` to the latest close.
    """

    before = closes.loc[: pd.Timestamp(start)]
    base = before.iloc[-1] if not before.empty else closes.iloc[0]

    return float(closes.iloc[-1] / base - 1.0)


class MarketService:
    def __init__(self, market: MarketDataRepository, *, review_days: int):
        self._market = market
        self._review_days = review_days

    def quote(self, ticker: str) -> Quote:
        return self.quotes((ticker,))[0]

    def quotes(self, tickers: tuple[str, ...]) -> list[Quote]:
        if not tickers:
            return []

        prices = self._market.get_prices(tickers)
        window = review_window(prices, self._review_days)

        quotes = []

        for ticker, rows in prices.groupby("ticker", sort=False):
            rows = rows.sort_values("date").set_index("date")

            last = rows.iloc[-1]
            previous = rows.iloc[-2] if len(rows) > 1 else last

            quotes.append(
                Quote(
                    ticker=ticker,
                    as_of=rows.index[-1].date(),
                    last=float(last["close"]),
                    previous_close=float(previous["close"]),
                    change=float(last["close"] - previous["close"]),
                    change_pct=float(
                        (last["close"] / previous["close"] - 1.0) * 100
                    ),
                    open=float(last["open"]),
                    high=float(last["high"]),
                    low=float(last["low"]),
                    volume=float(last["volume"]),
                    month_return_pct=return_since(
                        rows["close"], window.start
                    ) * 100,
                )
            )

        order = {ticker.upper(): index for index, ticker in enumerate(tickers)}

        return sorted(quotes, key=lambda quote: order.get(quote.ticker, 0))

    def candles(self, ticker: str, *, days: int = 180) -> CandleSeries:
        symbol = ticker.strip().upper()

        rows = (
            self._market.get_prices((symbol,))
            .sort_values("date")
            .set_index("date")
        )

        # Overlays are computed on the full history and
        # sliced afterwards, so the first visible candle
        # already has warmed-up averages.
        overlays = pd.DataFrame(
            {
                "ma_fast": moving_average(rows, FAST_WINDOW),
                "ma_slow": moving_average(rows, SLOW_WINDOW),
                "vwap": rolling_vwap(rows, VWAP_WINDOW),
                "twap": rolling_twap(rows, TWAP_WINDOW),
            }
        )

        start = rows.index.max() - timedelta(days=days)
        visible = rows.join(overlays).loc[start:]

        def optional(value: float) -> float | None:
            return None if pd.isna(value) else float(value)

        return CandleSeries(
            ticker=symbol,
            fast=FAST_WINDOW,
            slow=SLOW_WINDOW,
            vwap_window=VWAP_WINDOW,
            twap_window=TWAP_WINDOW,
            candles=[
                Candle(
                    time=day.date(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    ma_fast=optional(row["ma_fast"]),
                    ma_slow=optional(row["ma_slow"]),
                    vwap=optional(row["vwap"]),
                    twap=optional(row["twap"]),
                )
                for day, row in visible.iterrows()
            ],
        )
