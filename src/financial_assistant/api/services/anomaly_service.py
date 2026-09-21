from __future__ import annotations

import threading
import time
from datetime import datetime, time as clock, timezone

import pandas as pd

from financial_assistant.anomaly_detection import (
    PairAnomaly,
    SignalAnomaly,
    StrategyKind,
    detect_signal_anomalies,
    fit_pairs,
    monitor_pairs,
    pair_anomaly_to_event,
    signal_anomaly_to_event,
)
from financial_assistant.anomaly_detection.scalable import fit_large_universe
from financial_assistant.api.errors import NotFound
from financial_assistant.api.models import Anomaly
from financial_assistant.api.repositories import (
    InstrumentRepository,
    MarketDataRepository,
    PortfolioRepository,
)
from financial_assistant.api.schemas import (
    PairFitView,
    PairScan,
    PairSpread,
    SpreadPoint,
    StrategyCard,
)
from financial_assistant.api.services.market_service import review_window
from financial_assistant.domain import AnomalyEvent


# US cash session close, late enough to be correct in
# both daylight-saving regimes. A daily bar is not
# observable before it.
SESSION_CLOSE_UTC = clock(21, 0)

CACHE_SECONDS = 600

# Above this many securities the exhaustive fitter is no longer
# an option (3,000 names are 4.5 million pairs), and the scan
# switches to the bounded one. See anomaly_detection.scalable.
LARGE_UNIVERSE = 400
PEERS_PER_FOCUS_TICKER = 8
PEERS_PER_UNIVERSE_TICKER = 5


STRATEGIES: tuple[dict[str, str], ...] = (
    {
        "key": StrategyKind.VWAP.value,
        "category": "Execution",
        "name": "VWAP",
        "description": (
            "Slices large orders along the historical volume curve, "
            "trading heaviest when the market is deepest."
        ),
        "assumption": "Today's volume curve looks like history.",
        "detects": (
            "Volume spikes and closes stretched away from the "
            "20-day VWAP."
        ),
    },
    {
        "key": StrategyKind.TWAP.value,
        "category": "Execution",
        "name": "TWAP",
        "description": (
            "Splits an order into equal slices spread evenly through "
            "time, ignoring volume."
        ),
        "assumption": "Price does not drift while the order works.",
        "detects": (
            "5-session TWAP fills far from the arrival price."
        ),
    },
    {
        "key": StrategyKind.TREND.value,
        "category": "Trend following",
        "name": "MA Cross",
        "description": (
            "Enters and exits when the fast moving average crosses "
            "the slow one."
        ),
        "assumption": "A cross starts a trend that persists.",
        "detects": "MA7/MA25 crosses, and whipsaws that reverse them.",
    },
    {
        "key": StrategyKind.PAIRS.value,
        "category": "Statistical arbitrage",
        "name": "Pairs",
        "description": (
            "Buys the underperformer and shorts the outperformer of "
            "two cointegrated stocks."
        ),
        "assumption": "The spread always reverts to its mean.",
        "detects": (
            "Cointegration spreads beyond 2 sigma versus a frozen "
            "252-session fit."
        ),
    },
)


def session_close(day) -> datetime:
    return datetime.combine(day, SESSION_CLOSE_UTC, tzinfo=timezone.utc)


def severity(z_score: float, threshold: float) -> float:
    return min(1.0, abs(z_score) / (3.0 * threshold))


class AnomalyService:
    """
    Runs every strategy monitor over the review window
    and exposes the result as one blotter.
    """

    def __init__(
        self,
        portfolios: PortfolioRepository,
        market: MarketDataRepository,
        instruments: InstrumentRepository,
        *,
        review_days: int,
        benchmark: str,
        formation_observations: int,
        corr_min: float,
        alpha: float,
        entry: float,
        corr_min_same_sector: float | None = None,
    ):
        self._portfolios = portfolios
        self._market = market
        self._instruments = instruments

        self._review_days = review_days
        self._benchmark = benchmark
        self._formation_observations = formation_observations
        self._corr_min = corr_min
        self._corr_min_same_sector = corr_min_same_sector
        self._alpha = alpha
        self._entry = entry

        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._flights: dict[tuple, threading.Lock] = {}
        self._events: dict[str, AnomalyEvent] = {}

    # -------------------------------------------------
    # Queries
    # -------------------------------------------------

    def list(
        self,
        *,
        ticker: str | None = None,
        strategy: StrategyKind | None = None,
    ) -> list[Anomaly]:
        """
        Anomalies for one ticker, or for the whole book
        when no ticker is given.
        """

        tickers = (
            self._portfolios.load().tickers
            if ticker is None
            else (ticker.strip().upper(),)
        )

        anomalies = [
            anomaly
            for symbol in tickers
            for anomaly in self._signals(symbol)
        ]

        if tickers:
            anomalies.extend(
                anomaly
                for anomaly in self.pair_scan(focus=tickers).anomalies
                if ticker is None
                or tickers[0] in (anomaly.ticker, *anomaly.related_tickers)
            )

        if strategy is not None:
            anomalies = [a for a in anomalies if a.strategy == strategy]

        return sorted(
            anomalies,
            key=lambda a: (a.observed_on, a.severity),
            reverse=True,
        )

    def counts_by_ticker(self) -> dict[str, int]:
        counts: dict[str, int] = {}

        for anomaly in self.list():
            for symbol in (anomaly.ticker, *anomaly.related_tickers):
                counts[symbol] = counts.get(symbol, 0) + 1

        return counts

    def strategies(self, *, ticker: str | None = None) -> list[StrategyCard]:
        anomalies = self.list(ticker=ticker)

        return [
            StrategyCard(
                **card,
                anomaly_count=sum(
                    1 for a in anomalies if a.strategy.value == card["key"]
                ),
            )
            for card in STRATEGIES
        ]

    def find(
        self,
        anomaly_id: str,
        *,
        ticker: str | None = None,
    ) -> tuple[Anomaly, AnomalyEvent]:
        """
        Resolve a blotter row back to the neutral
        attention event the investigation consumes.
        """

        for anomaly in self.list(ticker=ticker):
            if anomaly.anomaly_id == anomaly_id:
                return anomaly, self._events[anomaly_id]

        raise NotFound(f"Unknown anomaly {anomaly_id}.")

    def event(self, anomaly_id: str) -> AnomalyEvent | None:
        """The attention event of an anomaly already detected."""

        return self._events.get(anomaly_id)

    # -------------------------------------------------
    # Pairs
    # -------------------------------------------------

    def pair_scan(self, *, focus: tuple[str, ...]) -> PairScan:
        """
        Cointegration scan of the focus tickers against
        the book and the peer universe.

        Relationships are fitted on the formation window
        strictly before the review window and then only
        observed, never re-estimated, inside it.
        """

        focus_set = frozenset(t.strip().upper() for t in focus)

        universe = tuple(
            dict.fromkeys(
                (
                    *focus_set,
                    *self._portfolios.load().tickers,
                    *self._instruments.universe,
                )
            )
        )

        return self._cached(
            ("pairs", tuple(sorted(focus_set)), universe),
            lambda: self._scan_pairs(focus_set, universe),
        )

    def pair_spread(self, ticker_a: str, ticker_b: str) -> PairSpread:
        a, b = ticker_a.strip().upper(), ticker_b.strip().upper()

        prices = self._market.get_prices((a, b))
        window = review_window(prices, self._review_days)
        formation = self._formation_dates(prices, window.start)

        fits = fit_pairs(
            prices,
            start=formation[0],
            end=formation[-1],
            corr_min=-1.0,
            alpha=1.0,
        )

        if not fits:
            raise NotFound(f"No pair relationship for {a}/{b}.")

        fit = fits[0]

        zscores, _ = monitor_pairs(
            prices,
            fits,
            start=formation[0],
            end=window.end,
            entry=self._entry,
        )

        series = zscores.iloc[:, 0].dropna()

        return PairSpread(
            ticker_a=fit.ticker_a,
            ticker_b=fit.ticker_b,
            beta=fit.beta,
            entry=self._entry,
            formation_end=fit.formation_end,
            points=[
                SpreadPoint(time=day.date(), z_score=float(value))
                for day, value in series.items()
            ],
        )

    # -------------------------------------------------
    # Internals
    # -------------------------------------------------

    def _signals(self, ticker: str) -> list[Anomaly]:
        return self._cached(
            ("signals", ticker),
            lambda: self._detect_signals(ticker),
        )

    def _detect_signals(self, ticker: str) -> list[Anomaly]:
        prices = self._market.get_prices((ticker,))
        window = review_window(prices, self._review_days)

        detected = detect_signal_anomalies(
            prices,
            ticker=ticker,
            start=window.start,
            end=window.end,
        )

        return [self._register_signal(anomaly) for anomaly in detected]

    def _scan_pairs(
        self,
        focus: frozenset[str],
        universe: tuple[str, ...],
    ) -> PairScan:
        large = len(universe) > LARGE_UNIVERSE
        whole = len(focus) > LARGE_UNIVERSE

        # Only what the manager is looking at is worth a
        # download inside a request. The rest of a large
        # universe is read as `make universe` left it.
        prices = self._market.get_available(
            universe,
            refresh=(
                None
                if not large
                else (
                    *(() if whole else tuple(focus)),
                    *self._portfolios.load().tickers,
                    self._benchmark,
                )
            ),
        )

        # The benchmark defines the trading calendar, so a
        # newly listed peer cannot shorten the window.
        calendar = self._market.get_prices((self._benchmark,))
        window = review_window(calendar, self._review_days)
        formation = self._formation_dates(calendar, window.start)

        if prices["ticker"].nunique() > LARGE_UNIVERSE:
            # Years of history nobody fits on would only slow
            # the pivot down. A calendar margin covers markets
            # whose holidays differ from the benchmark's.
            recent = prices.loc[
                pd.to_datetime(prices["date"])
                >= pd.Timestamp(formation[0]) - pd.Timedelta(days=45)
            ]

            fits = fit_large_universe(
                recent,
                start=pd.Timestamp(formation[0]) - pd.Timedelta(days=45),
                end=formation[-1],
                corr_min=self._corr_min,
                alpha=self._alpha,
                focus=None if whole else focus,
                sectors=self._instruments.sectors,
                corr_min_same_sector=self._corr_min_same_sector,
                groups=self._instruments.groups,
                formation_observations=self._formation_observations,
                max_peers_per_ticker=(
                    PEERS_PER_UNIVERSE_TICKER
                    if whole
                    else PEERS_PER_FOCUS_TICKER
                ),
            )

            legs = {t for fit in fits for t in (fit.ticker_a, fit.ticker_b)}
            monitored = recent.loc[recent["ticker"].isin(legs)]

        else:
            fits = fit_pairs(
                prices,
                start=formation[0],
                end=formation[-1],
                corr_min=self._corr_min,
                alpha=self._alpha,
                focus=focus,
                sectors=self._instruments.sectors,
                corr_min_same_sector=self._corr_min_same_sector,
            )

            monitored = prices

        zscores, detected = monitor_pairs(
            monitored,
            fits,
            start=window.start,
            end=window.end,
            entry=self._entry,
        )

        flagged = {(a.ticker_a, a.ticker_b) for a in detected}

        def latest_z(pair: str) -> float | None:
            if pair not in zscores:
                return None

            series = zscores[pair].dropna()

            return None if series.empty else float(series.iloc[-1])

        return PairScan(
            focus=sorted(focus),
            universe_size=prices["ticker"].nunique(),
            formation_start=formation[0],
            formation_end=formation[-1],
            monitoring_start=window.start,
            monitoring_end=window.end,
            entry=self._entry,
            fits=[
                PairFitView(
                    ticker_a=fit.ticker_a,
                    ticker_b=fit.ticker_b,
                    correlation=fit.correlation,
                    beta=fit.beta,
                    pvalue=fit.pvalue,
                    half_life_days=fit.half_life_days,
                    z_score=latest_z(f"{fit.ticker_a}/{fit.ticker_b}"),
                    flagged=(fit.ticker_a, fit.ticker_b) in flagged,
                )
                for fit in fits
            ],
            anomalies=[self._register_pair(anomaly) for anomaly in detected],
        )

    def _formation_dates(self, prices: pd.DataFrame, review_start) -> list:
        sessions = (
            pd.to_datetime(prices["date"])
            .drop_duplicates()
            .sort_values()
        )

        before = sessions[sessions < pd.Timestamp(review_start)]
        selected = before.iloc[-self._formation_observations:]

        if len(selected) < 2:
            raise NotFound("Not enough history to fit pair relationships.")

        return [day.date() for day in selected]

    def _register_signal(self, anomaly: SignalAnomaly) -> Anomaly:
        self._events[anomaly.anomaly_id] = signal_anomaly_to_event(
            anomaly,
            observed_at=session_close(anomaly.observed_on),
        )

        return Anomaly(
            anomaly_id=anomaly.anomaly_id,
            ticker=anomaly.ticker,
            strategy=anomaly.strategy,
            kind=anomaly.kind.value,
            observed_on=anomaly.observed_on,
            z_score=anomaly.z_score,
            threshold=anomaly.threshold,
            severity=severity(anomaly.z_score, anomaly.threshold),
            direction=anomaly.direction,
            summary=anomaly.summary,
            metrics=anomaly.metrics,
        )

    def _register_pair(self, anomaly: PairAnomaly) -> Anomaly:
        event = pair_anomaly_to_event(
            anomaly,
            observed_at=session_close(anomaly.monitoring_end),
        )

        self._events[anomaly.anomaly_id] = event

        return Anomaly(
            anomaly_id=anomaly.anomaly_id,
            ticker=anomaly.ticker_a,
            related_tickers=(anomaly.ticker_b,),
            strategy=StrategyKind.PAIRS,
            kind=event.anomaly_type,
            observed_on=anomaly.monitoring_end,
            z_score=anomaly.z_score,
            threshold=anomaly.threshold,
            severity=severity(anomaly.max_abs_z, anomaly.threshold),
            direction=anomaly.relative_direction,
            summary=(
                f"{anomaly.ticker_a}/{anomaly.ticker_b} spread at "
                f"z={anomaly.z_score:+.2f}, beyond "
                f"{anomaly.threshold:.1f} sigma for "
                f"{anomaly.n_days_flagged} sessions since "
                f"{anomaly.first_flag.isoformat()}"
            ),
            metrics={
                "first_flag": anomaly.first_flag.isoformat(),
                "n_days_flagged": anomaly.n_days_flagged,
                "max_abs_z": anomaly.max_abs_z,
                **(
                    {"peak_date": anomaly.peak_date.isoformat()}
                    if anomaly.peak_date
                    else {}
                ),
                "beta": anomaly.beta,
                "formation_start": anomaly.formation_start.isoformat(),
                "formation_end": anomaly.formation_end.isoformat(),
            },
        )

    def _cached(self, key: tuple, compute):
        """
        Memoise, and compute each key ONCE at a time.

        The first paint of the desk asks four endpoints for the
        book's anomalies at the same moment. Without the per-key
        lock each of them ran the whole scan, in parallel,
        fighting over the same data: 18 s instead of 5.
        """

        with self._lock:
            hit = self._cache.get(key)

            if hit is not None and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]

            flight = self._flights.setdefault(key, threading.Lock())

        with flight:
            # Whoever waited finds the answer already there.
            with self._lock:
                hit = self._cache.get(key)

                if hit is not None and time.time() - hit[0] < CACHE_SECONDS:
                    return hit[1]

            value = compute()

            with self._lock:
                self._cache[key] = (time.time(), value)
                self._flights.pop(key, None)

        return value

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
