from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from financial_assistant.api.errors import Conflict, DeskError, NotFound
from financial_assistant.api.models import Portfolio, Position
from financial_assistant.api.repositories import (
    InstrumentRepository,
    MarketDataRepository,
    PortfolioRepository,
)
from financial_assistant.api.schemas import (
    AddPositionResponse,
    PortfolioView,
    PositionView,
)
from financial_assistant.api.services.anomaly_service import AnomalyService
from financial_assistant.api.services.market_service import (
    return_since,
    review_window,
)
from financial_assistant.portfolio.returns import (
    analyze_portfolio,
    simulate_overlay,
)
from financial_assistant.portfolio.service import market_context


# Every input price of every holding is part of a result's
# provenance. It is hashed and counted for the browser, not
# shipped: a 22-name book is 25,000 observations.
def _compact(result: dict[str, Any]) -> dict[str, Any]:
    provenance = result.get("provenance")

    if isinstance(provenance, dict) and "inputs" in provenance:
        result = {
            **result,
            "provenance": {
                **{k: v for k, v in provenance.items() if k != "inputs"},
                "observations": {
                    ticker: len(rows)
                    for ticker, rows in provenance["inputs"].items()
                },
            },
        }

    return result


class PortfolioService:
    def __init__(
        self,
        portfolios: PortfolioRepository,
        instruments: InstrumentRepository,
        market: MarketDataRepository,
        anomalies: AnomalyService,
        *,
        benchmark: str,
        review_days: int,
    ):
        self._portfolios = portfolios
        self._instruments = instruments
        self._market = market
        self._anomalies = anomalies
        self._benchmark = benchmark
        self._review_days = review_days

    def view(self) -> PortfolioView:
        return self._view(self._portfolios.load())

    def add_position(self, ticker: str, shares: float) -> AddPositionResponse:
        """
        Add a holding, then immediately test it for
        cointegrated partners in the book and the peer
        universe.
        """

        symbol = ticker.strip().upper()
        portfolio = self._portfolios.load()

        if symbol in portfolio.tickers:
            raise Conflict(f"{symbol} is already in the portfolio.")

        # Raises NotFound for an unknown symbol before
        # anything is persisted.
        self._market.get_prices((symbol,))

        position = Position(
            ticker=symbol,
            name=self._instruments.describe(symbol).name,
            shares=shares,
            added_at=datetime.now(timezone.utc),
        )

        portfolio = self._portfolios.save(
            portfolio.model_copy(
                update={"positions": (*portfolio.positions, position)}
            )
        )

        self._anomalies.invalidate()

        return AddPositionResponse(
            portfolio=self._view(portfolio),
            pair_scan=self._anomalies.pair_scan(focus=(symbol,)),
        )

    def remove_position(self, ticker: str) -> PortfolioView:
        symbol = ticker.strip().upper()
        portfolio = self._portfolios.load()

        if symbol not in portfolio.tickers:
            raise NotFound(f"{symbol} is not in the portfolio.")

        portfolio = self._portfolios.save(
            portfolio.model_copy(
                update={
                    "positions": tuple(
                        p for p in portfolio.positions if p.ticker != symbol
                    )
                }
            )
        )

        self._anomalies.invalidate()

        return self._view(portfolio)

    def reset(self) -> PortfolioView:
        portfolio = self._portfolios.reset()
        self._anomalies.invalidate()

        return self._view(portfolio)

    def set_weights(
        self,
        positions: list[tuple[str, float]],
        *,
        notional: float,
        name: str | None = None,
    ) -> PortfolioView:
        """
        Replace the book with one stated as weights.

        Weights must sum to one. Each becomes a share count at
        the latest visible close, so on a replay date the book
        is sized with the prices of that day.
        """

        tickers = [ticker.strip().upper() for ticker, _ in positions]

        if len(set(tickers)) != len(tickers):
            raise DeskError("Tickers must be unique.")

        total = sum(weight for _, weight in positions)

        if abs(total - 1.0) > 0.001:
            raise DeskError(
                f"Weights must sum to 1 (they sum to {total:.4f})."
            )

        # Raises NotFound for an unknown symbol before anything
        # is persisted.
        prices = self._market.get_prices(tuple(tickers))

        last = (
            prices.sort_values("date")
            .groupby("ticker")["close"]
            .last()
        )

        now = datetime.now(timezone.utc)
        current = self._portfolios.load()

        book = tuple(
            Position(
                ticker=ticker,
                name=self._instruments.describe(ticker).name,
                shares=notional * weight / total / float(last[ticker]),
                added_at=now,
            )
            for ticker, (_, weight) in zip(tickers, positions)
            if weight > 0
        )

        portfolio = self._portfolios.save(
            current.model_copy(
                update={"positions": book, "name": name or current.name}
            )
        )

        self._anomalies.invalidate()

        return self._view(portfolio)

    # -------------------------------------------------
    # Analysis workspace
    # -------------------------------------------------

    def weights(self) -> dict[str, Any]:
        """
        The book as the analytical portfolio: market-value
        weights at the latest visible close.
        """

        view = self.view()

        return {
            "id": "book",
            "name": view.name,
            "as_of": view.window.end.isoformat(),
            "positions": [
                {"ticker": p.ticker, "weight": p.weight_pct / 100}
                for p in view.positions
            ],
        }

    def analysis(self) -> dict[str, Any]:
        portfolio = self.weights()

        if not portfolio["positions"]:
            return {"status": "unavailable", "reason": "The book is empty."}

        tickers = tuple(p["ticker"] for p in portfolio["positions"])

        return _compact(
            analyze_portfolio(
                self._prices(tickers),
                portfolio,
                portfolio["as_of"],
            )
        )

    def simulate(
        self,
        ticker_a: str,
        ticker_b: str,
        *,
        gross_overlay: float,
        lookback: int,
    ) -> dict[str, Any]:
        """
        What the book would have looked like with a small
        A-relative-to-B overlay. Descriptive, never a forecast.
        """

        portfolio = self.weights()

        if not portfolio["positions"]:
            return {"status": "unavailable", "reason": "The book is empty."}

        a, b = ticker_a.strip().upper(), ticker_b.strip().upper()
        tickers = (*(p["ticker"] for p in portfolio["positions"]), a, b)

        return _compact(
            simulate_overlay(
                self._prices(tickers),
                portfolio,
                {"ticker_a": a, "ticker_b": b},
                portfolio["as_of"],
                gross_overlay,
                lookback,
            )
        )

    def market(self, tickers: list[str]) -> dict[str, Any]:
        symbols = tuple(t.strip().upper() for t in tickers)
        as_of = self.view().window.end.isoformat()

        return market_context(symbols, as_of, self._prices(symbols))

    def _prices(self, tickers: tuple[str, ...]) -> pd.DataFrame:
        return self._market.get_available(tuple(dict.fromkeys(tickers)))

    # -------------------------------------------------

    def _view(self, portfolio: Portfolio) -> PortfolioView:
        benchmark = (
            self._market.get_prices((self._benchmark,))
            .sort_values("date")
            .set_index("date")["close"]
        )

        window = review_window(benchmark.reset_index(), self._review_days)
        benchmark_return = return_since(benchmark, window.start)

        if not portfolio.positions:
            return PortfolioView(
                name=portfolio.name,
                manager=portfolio.manager,
                window=window,
                benchmark=self._benchmark,
                market_value=0.0,
                day_change_pct=0.0,
                month_return_pct=0.0,
                benchmark_return_pct=benchmark_return * 100,
                active_return_pct=-benchmark_return * 100,
                positions=[],
            )

        prices = self._market.get_prices(portfolio.tickers)
        counts = self._anomalies.counts_by_ticker()

        rows = []

        for position in portfolio.positions:
            closes = (
                prices.loc[prices["ticker"] == position.ticker]
                .sort_values("date")
                .set_index("date")["close"]
            )

            last = float(closes.iloc[-1])
            previous = float(closes.iloc[-2]) if len(closes) > 1 else last
            month_return = return_since(closes, window.start)

            rows.append(
                {
                    "position": position,
                    "last": last,
                    "previous_value": position.shares * previous,
                    "value": position.shares * last,
                    "start_value": position.shares * last / (1 + month_return),
                    "day": last / previous - 1.0,
                    "month": month_return,
                }
            )

        value = sum(row["value"] for row in rows)
        start_value = sum(row["start_value"] for row in rows)
        previous_value = sum(row["previous_value"] for row in rows)

        month_return = value / start_value - 1.0

        return PortfolioView(
            name=portfolio.name,
            manager=portfolio.manager,
            window=window,
            benchmark=self._benchmark,
            market_value=value,
            day_change_pct=(value / previous_value - 1.0) * 100,
            month_return_pct=month_return * 100,
            benchmark_return_pct=benchmark_return * 100,
            active_return_pct=(month_return - benchmark_return) * 100,
            positions=[
                PositionView(
                    ticker=row["position"].ticker,
                    name=row["position"].name or row["position"].ticker,
                    shares=row["position"].shares,
                    last=row["last"],
                    market_value=row["value"],
                    weight_pct=row["value"] / value * 100,
                    day_change_pct=row["day"] * 100,
                    month_return_pct=row["month"] * 100,
                    # Share of the book's return that came
                    # from this holding.
                    contribution_pct=(
                        (row["value"] - row["start_value"])
                        / start_value
                        * 100
                    ),
                    anomaly_count=counts.get(row["position"].ticker, 0),
                )
                for row in rows
            ],
        )
