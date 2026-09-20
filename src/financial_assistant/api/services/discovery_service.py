from __future__ import annotations

import json
import threading
from hashlib import sha1
from pathlib import Path

import numpy as np
import pandas as pd

from financial_assistant.analytics import (
    PairAnalogueBase,
    build_pair_analogue_base,
)
from financial_assistant.api.relevance import company_aliases, relevance
from financial_assistant.api.repositories import (
    InstrumentRepository,
    MarketDataRepository,
    PortfolioRepository,
)
from financial_assistant.api.schemas import Discovery, FunnelStep, Setup
from financial_assistant.api.services.anomaly_service import AnomalyService
from financial_assistant.api.services.news_service import NewsService
from financial_assistant.api.services.postmortem_service import relationship_of


LIQUIDITY_SESSIONS = 20


class DiscoveryService:
    """
    Story 3: nobody asked about anything.

    The pipeline is inverted: start from the whole investable
    universe, keep what is related, then what is unusual, then
    what history says is worth a look, and surface the best.
    Every number in the funnel is a real count from this run.
    """

    def __init__(
        self,
        anomalies: AnomalyService,
        news: NewsService,
        market: MarketDataRepository,
        portfolios: PortfolioRepository,
        instruments: InstrumentRepository,
        *,
        cache_dir: Path,
        formation_observations: int,
        corr_min: float,
        alpha: float,
        entry: float,
        min_liquidity_musd: float,
        analogue_builder=build_pair_analogue_base,
    ):
        self._anomalies = anomalies
        self._news = news
        self._market = market
        self._portfolios = portfolios
        self._instruments = instruments

        self._cache_dir = cache_dir
        self._formation_observations = formation_observations
        self._corr_min = corr_min
        self._alpha = alpha
        self._entry = entry
        self._min_liquidity_musd = min_liquidity_musd
        self._build_analogues = analogue_builder

        self._lock = threading.Lock()

    def scan(self) -> Discovery:
        holdings = set(self._portfolios.load().tickers)

        universe = tuple(dict.fromkeys((*holdings, *self._instruments.universe)))

        prices = self._market.get_available(universe)
        securities = int(prices["ticker"].nunique())

        scan = self._anomalies.pair_scan(focus=universe)
        base = self._analogue_base(prices)

        unusual = [
            anomaly
            for anomaly in scan.anomalies
            if abs(anomaly.z_score) > self._entry
        ]

        liquidity = self._liquidity(prices)

        setups = []

        for anomaly in unusual:
            a, b = anomaly.ticker, anomaly.related_tickers[0]
            relationship = relationship_of(scan, a, b)

            if relationship is None:
                continue

            # A above equilibrium: A is rich, B is cheap.
            long, short = (b, a) if anomaly.z_score > 0 else (a, b)
            outcome = base.outcome(anomaly.z_score)

            setups.append(
                Setup(
                    anomaly=anomaly,
                    long=long,
                    short=short,
                    z_score=anomaly.z_score,
                    relationship=relationship,
                    outcome=outcome,
                    expected_horizon=self._horizon(relationship.half_life_days),
                    headlines=self._headlines(anomaly),
                    liquidity_musd=min(liquidity.get(a, 0.0), liquidity.get(b, 0.0)),
                    why_connected=[
                        f"Returns correlated {relationship.correlation:.2f} over "
                        f"the {self._formation_observations} sessions before "
                        "the review window.",
                        f"Cointegrated (Engle-Granger p = {relationship.pvalue:.4f}): "
                        f"log {a} tracks {relationship.beta:.2f} × log {b}, and "
                        "deviations have closed with a half-life of "
                        + (
                            f"{relationship.half_life_days:.1f} sessions."
                            if relationship.half_life_days
                            else "unknown length."
                        ),
                        "The economic link (products, customers, competitors) is "
                        "reconstructed from the news in the reasoning view.",
                    ],
                    invalidation=[
                        f"The spread moves beyond {abs(anomaly.z_score) + 1:.1f}σ "
                        "instead of closing: the relationship is breaking, not "
                        "stretching.",
                        f"The reasoning view finds a company-specific, lasting "
                        f"cause in {a} or {b}: then the gap is a repricing, not "
                        "a dislocation.",
                        "No convergence after two half-lives.",
                    ],
                    score=self._score(anomaly.z_score, outcome),
                )
            )

        liquid = [s for s in setups if s.liquidity_musd >= self._min_liquidity_musd]

        favourable = [
            s
            for s in liquid
            if s.outcome is not None
            and s.outcome.expected_abnormal_return_pct > 0
        ]

        favourable.sort(key=lambda setup: setup.score, reverse=True)

        # Discovery means what the manager is NOT already
        # looking at. A relationship involving a holding was
        # found by the post-mortem, from the same data on the
        # same day, so it is listed apart instead of being
        # announced a second time.
        def held(setup: Setup) -> bool:
            return bool(
                holdings & {setup.anomaly.ticker, *setup.anomaly.related_tickers}
            )

        new = [setup for setup in favourable if not held(setup)]

        return Discovery(
            as_of=scan.monitoring_end,
            funnel=[
                FunnelStep(label="securities scanned", count=securities),
                FunnelStep(
                    label="possible relationships",
                    count=securities * (securities - 1) // 2,
                ),
                FunnelStep(
                    label="historically co-moving",
                    count=self._co_moving(prices, scan),
                ),
                FunnelStep(label="cointegrated", count=len(scan.fits)),
                FunnelStep(label="unusual today", count=len(setups)),
                FunnelStep(label="liquid enough", count=len(liquid)),
                FunnelStep(
                    label="favourable in historical analogues",
                    count=len(favourable),
                ),
                FunnelStep(label="new to you", count=len(new)),
            ],
            setups=new,
            on_your_desk=[setup for setup in favourable if held(setup)],
            analogue_breaks=len(base.breaks),
            analogue_period=(
                f"{base.first_as_of} → {base.last_as_of}"
                if base.first_as_of
                else "no history"
            ),
        )

    # -------------------------------------------------

    @staticmethod
    def _score(z_score: float, outcome) -> float:
        if outcome is None:
            return 0.0

        return abs(z_score) * outcome.reversion_pct / 100

    @staticmethod
    def _horizon(half_life: float | None) -> str:
        if not half_life:
            return "unknown"

        low = max(1, round(half_life))
        high = max(low + 1, round(half_life * 2))

        return f"{low}–{high} trading days"

    def _headlines(self, anomaly) -> int:
        """
        Headlines naming either company before the evidence
        cutoff: whether there is anything to explain the move.
        """

        items = self._news.around(anomaly).admissible
        named = 0

        for ticker in (anomaly.ticker, *anomaly.related_tickers):
            aliases = company_aliases(
                ticker, self._instruments.describe(ticker).name
            )

            named += sum(
                1
                for item in items
                if item.ticker == ticker and relevance(item, aliases) == 2
            )

        return named

    def _liquidity(self, prices: pd.DataFrame) -> dict[str, float]:
        recent = prices.sort_values("date").groupby("ticker").tail(LIQUIDITY_SESSIONS)
        dollars = (recent["close"] * recent["volume"]).groupby(recent["ticker"]).mean()

        return (dollars / 1e6).to_dict()

    def _co_moving(self, prices: pd.DataFrame, scan) -> int:
        closes = (
            prices.assign(date=lambda f: pd.to_datetime(f["date"]))
            .pivot_table(index="date", columns="ticker", values="close")
            .sort_index()
            .loc[str(scan.formation_start): str(scan.formation_end)]
            .dropna(axis=1)
        )

        correlations = np.log(closes).diff().corr().to_numpy()
        upper = correlations[np.triu_indices_from(correlations, k=1)]

        return int((upper >= self._corr_min).sum())

    def _analogue_base(self, prices: pd.DataFrame) -> PairAnalogueBase:
        """
        The walk-forward record takes tens of seconds to build
        and only changes when the universe or the latest
        session does, so it is kept on disk.
        """

        last = pd.to_datetime(prices["date"]).max().date()

        key = sha1(
            json.dumps(
                [
                    sorted(prices["ticker"].unique()),
                    last.isoformat(),
                    self._formation_observations,
                    self._corr_min,
                    self._alpha,
                    self._entry,
                ]
            ).encode()
        ).hexdigest()[:12]

        path = self._cache_dir / f"pairs-{key}.json"

        with self._lock:
            if path.is_file():
                return PairAnalogueBase.model_validate_json(path.read_text())

            base = self._build_analogues(
                prices,
                formation_observations=self._formation_observations,
                corr_min=self._corr_min,
                alpha=self._alpha,
                entry=self._entry,
            )

            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(base.model_dump_json())

            return base
