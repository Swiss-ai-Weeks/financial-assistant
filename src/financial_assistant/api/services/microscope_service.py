from __future__ import annotations

import pandas as pd

from financial_assistant.analytics import (
    HORIZONS,
    HorizonReading,
    PeerReading,
    read_horizon,
    read_peers,
    single_name_analogues,
)
from financial_assistant.api.errors import DeskError
from financial_assistant.api.repositories import (
    InstrumentRepository,
    MarketDataRepository,
    PortfolioRepository,
)
from financial_assistant.api.schemas import HorizonTick, MatrixRow, Microscope
from financial_assistant.api.services.anomaly_service import (
    LARGE_UNIVERSE,
    AnomalyService,
)


def describe(
    ticker: str,
    reading: HorizonReading,
    peers: tuple[PeerReading, ...],
) -> list[str]:
    """
    The reading in the order a trader asks: is it unusual,
    is it traded, is it alone.
    """

    statements = [
        f"{reading.abnormal_return_pct:+.1f}% abnormal return versus the "
        f"market model (β {reading.beta:.2f}): "
        + (
            f"{abs(reading.z_score):.1f}σ, unusual at this horizon."
            if reading.unusual
            else f"{abs(reading.z_score):.1f}σ, not unusual at this horizon."
        ),
        f"Volume {reading.volume_multiple:.1f}× normal"
        + (
            "."
            if reading.volume_unusual
            else ", within its usual range."
        ),
    ]

    if reading.unusual:
        alone = [peer for peer in peers if not peer.followed]
        together = [peer for peer in peers if peer.followed]

        for peer in alone:
            statements.append(
                f"{peer.ticker} has not followed the move despite "
                f"historically high co-movement (ρ {peer.correlation:.2f})."
            )

        if together and not alone:
            statements.append(
                "Its closest peers moved with it: this looks like a group "
                "move rather than a company-specific one."
            )

    return statements


class MicroscopeService:
    """
    Story 2: what is unusual about this security right now,
    where "right now" is whatever horizon the trader picks.
    """

    def __init__(
        self,
        market: MarketDataRepository,
        portfolios: PortfolioRepository,
        instruments: InstrumentRepository,
        anomalies: AnomalyService,
        *,
        benchmark: str,
    ):
        self._market = market
        self._portfolios = portfolios
        self._instruments = instruments
        self._anomalies = anomalies
        self._benchmark = benchmark

    def _ticks(
        self,
        prices: pd.DataFrame,
        ticker: str,
    ) -> tuple[list[HorizonTick], dict[str, HorizonReading]]:
        """One security at every horizon it has history for."""

        ticks = []
        readings: dict[str, HorizonReading] = {}

        for name in HORIZONS:
            try:
                readings[name] = read_horizon(
                    prices, ticker=ticker, benchmark=self._benchmark, horizon=name
                )
            except (ValueError, IndexError, KeyError):
                ticks.append(
                    HorizonTick(
                        horizon=name, z_score=None, unusual=False, available=False
                    )
                )
                continue

            ticks.append(
                HorizonTick(
                    horizon=name,
                    z_score=readings[name].z_score,
                    unusual=readings[name].unusual,
                    available=True,
                )
            )

        return ticks, readings

    def read(self, ticker: str, horizon: str) -> Microscope:
        symbol = ticker.strip().upper()

        if horizon not in HORIZONS:
            raise DeskError(f"horizon must be one of {sorted(HORIZONS)}")

        book = self._portfolios.load().tickers
        universe = self._instruments.universe

        # Peers are companies like this one. In a universe of
        # thousands that means its own sector; comparing a bank
        # with three thousand strangers only finds coincidences.
        if len(universe) > LARGE_UNIVERSE:
            sectors = self._instruments.sectors
            sector = sectors.get(symbol)

            if sector is not None:
                universe = tuple(t for t in universe if sectors.get(t) == sector)

        comparable = tuple(dict.fromkeys((*book, *universe)))

        # Raises NotFound for an unknown symbol.
        subject = self._market.get_prices((symbol, self._benchmark))

        # Only the book is worth a download inside a request.
        # The rest of a large universe is read as `make universe`
        # left it: a page view must never fetch 3,000 tickers.
        others = self._market.get_available(
            tuple(t for t in comparable if t not in (symbol, self._benchmark)),
            refresh=(
                None
                if len(self._instruments.universe) <= LARGE_UNIVERSE
                else book
            ),
        )

        prices = pd.concat([subject, others], ignore_index=True)

        ticks, readings = self._ticks(prices, symbol)

        if horizon not in readings:
            raise DeskError(
                f"Not enough history to judge {symbol} over {horizon}."
            )

        reading = readings[horizon]

        peers = read_peers(
            prices, ticker=symbol, benchmark=self._benchmark, horizon=horizon
        )

        recent = self._anomalies.list(ticker=symbol)

        return Microscope(
            ticker=symbol,
            as_of=pd.to_datetime(subject["date"]).max().date(),
            horizon=horizon,
            ticks=ticks,
            reading=reading,
            statements=describe(symbol, reading, peers),
            peers=list(peers),
            matrix=[
                MatrixRow(ticker=symbol, is_subject=True, ticks=ticks),
                *(
                    MatrixRow(
                        ticker=peer.ticker,
                        is_subject=False,
                        correlation=peer.correlation,
                        ticks=self._ticks(prices, peer.ticker)[0],
                    )
                    for peer in peers
                ),
            ],
            outcome=single_name_analogues(
                prices,
                ticker=symbol,
                benchmark=self._benchmark,
                sessions=reading.sessions,
                z_score=reading.z_score,
                pool=tuple(t for t in comparable if t != symbol),
            ),
            latest_anomaly=recent[0] if recent else None,
        )
