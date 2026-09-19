from __future__ import annotations

from datetime import datetime, timezone

from financial_assistant.api.errors import Conflict, NotFound
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
