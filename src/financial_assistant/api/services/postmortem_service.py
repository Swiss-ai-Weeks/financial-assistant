from __future__ import annotations

from datetime import timedelta

import pandas as pd

from financial_assistant.anomaly_detection import StrategyKind
from financial_assistant.api.models import (
    Investigation,
    InvestigationStatus,
)
from financial_assistant.api.repositories import (
    InvestigationRepository,
    MarketDataRepository,
    PortfolioRepository,
)
from financial_assistant.api.schemas import (
    Finding,
    PairScan,
    PostMortem,
    Relationship,
)
from financial_assistant.api.services.anomaly_service import AnomalyService
from financial_assistant.api.services.market_service import review_window


MISSED_SIGNALS = {
    "volume_spike": (
        "Volume left its historical curve on {date}. A VWAP schedule "
        "built on the old curve was mis-sized from that session."
    ),
    "vwap_deviation": (
        "The close detached from VWAP on {date}: fills benchmarked to "
        "VWAP stopped describing where the market settled."
    ),
    "twap_deviation": (
        "Price drifted through the execution horizon ending {date}. "
        "An evenly paced order kept trading into the move."
    ),
    "trend_cross": (
        "The moving averages crossed on {date}: the regime a "
        "trend follower trades had changed."
    ),
    "trend_whipsaw": (
        "The {date} cross reversed the previous one within days: a "
        "trend-following entry was stopped straight back out."
    ),
}


def relationship_of(scan: PairScan, a: str, b: str) -> Relationship | None:
    for fit in scan.fits:
        if (fit.ticker_a, fit.ticker_b) == (a, b):
            return Relationship(
                ticker_a=a,
                ticker_b=b,
                correlation=fit.correlation,
                beta=fit.beta,
                pvalue=fit.pvalue,
                half_life_days=fit.half_life_days,
                formation_start=scan.formation_start,
                formation_end=scan.formation_end,
            )

    return None


def confidence_of(run: Investigation) -> str | None:
    """
    How far the evidence carries the leading explanation.
    Deliberately coarse: three words a trader can act on.
    """

    if not run.hypotheses:
        return None

    best = run.hypotheses[0]

    if best.score <= 0:
        return "low"

    if best.supporting >= 2 and best.contradicting == 0 and best.score >= 1.0:
        return "high"

    return "medium"


class PostMortemService:
    """
    Story 1: not "here are your losers" but the abnormal
    relationships behind them, what they cost, when they
    became visible, and why they happened.
    """

    def __init__(
        self,
        anomalies: AnomalyService,
        portfolios: PortfolioRepository,
        market: MarketDataRepository,
        investigations: InvestigationRepository,
        *,
        review_days: int,
        benchmark: str,
    ):
        self._anomalies = anomalies
        self._portfolios = portfolios
        self._market = market
        self._investigations = investigations
        self._review_days = review_days
        self._benchmark = benchmark

    def review(self) -> PostMortem:
        portfolio = self._portfolios.load()

        calendar = self._market.get_prices((self._benchmark,))
        window = review_window(calendar, self._review_days)

        if not portfolio.positions:
            return PostMortem(
                window=window, currency="USD", total_impact=0.0, findings=[]
            )

        anomalies = self._anomalies.list()
        scan = self._anomalies.pair_scan(focus=portfolio.tickers)

        involved = tuple(
            dict.fromkeys(
                ticker
                for anomaly in anomalies
                for ticker in (anomaly.ticker, *anomaly.related_tickers)
            )
        )

        closes = (
            self._market.get_prices(involved or portfolio.tickers)
            .assign(date=lambda f: pd.to_datetime(f["date"]))
            .pivot_table(index="date", columns="ticker", values="close")
            .sort_index()
        )

        shares = {p.ticker: p.shares for p in portfolio.positions}
        explained = self._latest_investigations()

        findings = [
            self._finding(anomaly, closes, shares, scan, explained)
            for anomaly in anomalies
        ]

        findings.sort(key=lambda finding: finding.impact)

        return PostMortem(
            window=window,
            currency="USD",
            total_impact=self._total(findings, closes, shares),
            findings=findings,
        )

    # -------------------------------------------------

    def _finding(self, anomaly, closes, shares, scan, explained) -> Finding:
        is_pair = anomaly.strategy == StrategyKind.PAIRS

        signal_date = pd.Timestamp(
            anomaly.metrics.get("first_flag", anomaly.observed_on)
        )

        # The last close BEFORE the signal is what a manager
        # acting on it would have traded against.
        before = closes.loc[: signal_date - timedelta(days=1)]
        base = before.iloc[-1] if not before.empty else closes.iloc[0]
        last = closes.iloc[-1]

        returns = last / base - 1.0
        sessions_of_warning = int((closes.index > signal_date).sum())

        def money(ticker: str) -> float:
            return shares.get(ticker, 0.0) * float(last[ticker] - base[ticker])

        run = explained.get(anomaly.anomaly_id)

        common = {
            "anomaly": anomaly,
            "impact_since": base.name.date(),
            "signal_date": signal_date.date(),
            "sessions_of_warning": sessions_of_warning,
            "explanation": (
                run.hypotheses[0].text
                if run and run.hypotheses and run.hypotheses[0].score > 0
                else None
            ),
            "confidence": confidence_of(run) if run else None,
            "investigation_id": run.investigation_id if run else None,
        }

        if not is_pair:
            return Finding(
                headline=f"{anomaly.ticker} — {anomaly.kind.replace('_', ' ')}",
                statement=anomaly.summary,
                impact=money(anomaly.ticker),
                missed_signal=MISSED_SIGNALS.get(
                    anomaly.kind, "Signal on {date}."
                ).format(date=f"{signal_date:%b %d}"),
                **common,
            )

        a, b = anomaly.ticker, anomaly.related_tickers[0]
        relationship = relationship_of(scan, a, b)

        gap = float(returns[a] - returns[b]) * 100
        laggard, leader = (a, b) if gap < 0 else (b, a)

        impact = money(a) + money(b)
        hedged = self._hedged(a, b, shares, base, returns, relationship, impact)

        held = a if a in shares else b
        other = b if held == a else a

        return Finding(
            # The manager reads the pair from their own side,
            # whichever leg the regression happens to explain.
            headline=f"{held} / {other} — unusual divergence",
            statement=(
                f"{laggard} underperformed {leader} by {abs(gap):.1f}% since "
                f"{signal_date:%b %d}, {abs(anomaly.z_score):.1f}σ outside "
                "their historical relationship."
            ),
            impact=impact,
            hedged_impact=hedged,
            missed_signal=(
                f"The spread crossed {anomaly.threshold:.0f}σ on "
                f"{signal_date:%b %d}, {sessions_of_warning} sessions before "
                f"the end of the period. Risk view for a holder of {held}: "
                f"reduce, or hedge with {other}. Relative-value view: "
                f"long {laggard} / short {leader} once it stops widening."
            ),
            relationship=relationship,
            **common,
        )

    @staticmethod
    def _hedged(a, b, shares, base, returns, relationship, impact) -> float | None:
        """
        Impact had the held leg been hedged with the other at
        the fitted ratio from the signal onwards.

        log(A) = c + beta * log(B): one dollar of A is hedged
        by beta dollars of B, and one dollar of B by 1/beta
        dollars of A.
        """

        if relationship is None or (a in shares) == (b in shares):
            return None

        if a in shares:
            notional = shares[a] * float(base[a])
            hedge_return = relationship.beta * float(returns[b])
        else:
            notional = shares[b] * float(base[b])
            hedge_return = float(returns[a]) / relationship.beta

        return impact - notional * hedge_return

    @staticmethod
    def _total(findings: list[Finding], closes, shares) -> float:
        """
        Money lost on flagged holdings, each counted once from
        its EARLIEST signal. Findings overlap (a volume spike
        and a pair break can describe the same slide), so
        their impacts must not simply be added up.
        """

        earliest: dict[str, pd.Timestamp] = {}

        for finding in findings:
            signal = pd.Timestamp(finding.signal_date)

            for ticker in (finding.anomaly.ticker, *finding.anomaly.related_tickers):
                if ticker in shares:
                    earliest[ticker] = min(earliest.get(ticker, signal), signal)

        total = 0.0

        for ticker, signal in earliest.items():
            before = closes[ticker].loc[: signal - timedelta(days=1)].dropna()
            base = before.iloc[-1] if not before.empty else closes[ticker].dropna().iloc[0]

            total += shares[ticker] * float(closes[ticker].dropna().iloc[-1] - base)

        return total

    def _latest_investigations(self) -> dict[str, Investigation]:
        latest: dict[str, Investigation] = {}

        # Newest first: the first completed run per anomaly wins.
        for run in self._investigations.list():
            if run.status == InvestigationStatus.COMPLETED:
                latest.setdefault(run.anomaly.anomaly_id, run)

        return latest
