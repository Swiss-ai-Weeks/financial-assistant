from __future__ import annotations

import json
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path

import numpy as np
import pandas as pd

from financial_assistant.analytics import (
    PairAnalogueBase,
    build_pair_analogue_base,
)
from financial_assistant.api.models import NewsItem
from financial_assistant.api.relevance import company_aliases, relevance
from financial_assistant.api.repositories import (
    InstrumentRepository,
    MarketDataRepository,
    PortfolioRepository,
    StoredTriage,
    TriageRepository,
)
from financial_assistant.api.schemas import (
    Discovery,
    DiscoveryJob,
    FunnelStep,
    Setup,
    TriageView,
)
from financial_assistant.api.services.anomaly_service import (
    LARGE_UNIVERSE,
    AnomalyService,
)
from financial_assistant.api.services.news_service import NewsService
from financial_assistant.api.services.postmortem_service import relationship_of
from financial_assistant.llm import (
    LLMTransportError,
    StructuredLLM,
    TriageHeadline,
    TriageVerdict,
    triage_anomaly,
)
from financial_assistant.llm.causal_triage import MAX_HEADLINES, PROMPT_VERSION


LIQUIDITY_SESSIONS = 20

# The last scan of a record is 10 to 19 sessions before the
# latest one it was built for: 14 to 28 calendar days.
ANALOGUE_MIN_AGE_DAYS = 14
ANALOGUE_MAX_AGE_DAYS = 45

# Securities the walk-forward record is built from when the
# universe is too large to replay whole.
ANALOGUE_MAX_TICKERS = 160

# Above this many securities the analogue replay uses the
# batched cointegration engine.
BATCHED_ABOVE = 40

# Candidates whose news is read and triaged per scan.
MAX_CANDIDATES = 40


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
        corr_min_same_sector: float | None = None,
        analogue_builder=build_pair_analogue_base,
        triage_store: TriageRepository | None = None,
        llm_factory: Callable[[], StructuredLLM] | None = None,
        llm_available: Callable[[], bool] = lambda: False,
        llm_workers: int = 8,
    ):
        self._anomalies = anomalies
        self._news = news
        self._market = market
        self._portfolios = portfolios
        self._instruments = instruments

        self._cache_dir = cache_dir
        self._formation_observations = formation_observations
        self._corr_min = corr_min
        self._corr_min_same_sector = corr_min_same_sector
        self._alpha = alpha
        self._entry = entry
        self._min_liquidity_musd = min_liquidity_musd
        self._build_analogues = analogue_builder

        self._triage_store = triage_store
        self._llm_factory = llm_factory
        self._llm_available = llm_available
        self._llm_workers = llm_workers

        self._lock = threading.Lock()

        self._job = DiscoveryJob()
        self._job_lock = threading.Lock()

    # -------------------------------------------------
    # Background job
    # -------------------------------------------------

    def job(self) -> DiscoveryJob:
        with self._job_lock:
            return self._job.model_copy()

    def reset(self) -> None:
        """
        Forget the last result: the desk moved in time, so it
        describes a market that is no longer the visible one.
        A scan still running keeps its slot and finishes.
        """

        with self._job_lock:
            if self._job.status != "running":
                self._job = DiscoveryJob()

    def start(self) -> DiscoveryJob:
        """
        Start a scan unless one is already running, and return
        at once. Progress and the result are read with job().
        """

        with self._job_lock:
            if self._job.status == "running":
                return self._job.model_copy()

            self._job = DiscoveryJob(
                status="running",
                stage="Starting",
                started_at=datetime.now(timezone.utc).isoformat(),
            )

        threading.Thread(
            target=self._run_job,
            name="discovery",
            daemon=True,
        ).start()

        return self.job()

    def _run_job(self) -> None:
        started = time.perf_counter()

        try:
            discovery = self.scan()
            outcome = {"status": "completed", "discovery": discovery, "stage": "Done"}

        except Exception as error:
            outcome = {
                "status": "failed",
                "error": str(error) or type(error).__name__,
            }

        with self._job_lock:
            self._job = self._job.model_copy(
                update={**outcome, "seconds": round(time.perf_counter() - started, 1)}
            )

    def _stage(self, text: str) -> None:
        with self._job_lock:
            if self._job.status == "running":
                self._job = self._job.model_copy(update={"stage": text})

    # -------------------------------------------------

    def scan(self) -> Discovery:
        holdings = set(self._portfolios.load().tickers)

        universe = tuple(dict.fromkeys((*holdings, *self._instruments.universe)))

        self._stage(f"Loading prices for {len(universe)} securities")

        # A universe of thousands is read from disk as `make
        # universe` left it; only the book is refreshed here.
        prices = self._market.get_available(
            universe,
            refresh=(
                None
                if len(universe) <= LARGE_UNIVERSE
                else tuple(holdings)
            ),
        )
        securities = int(prices["ticker"].nunique())

        # Of the millions of possible pairs only each security's
        # closest co-movers are tested: say what is being done.
        self._stage(
            f"Finding co-movers among {securities:,} securities and "
            "testing them for cointegration"
        )
        scan = self._anomalies.pair_scan(focus=universe)

        self._stage(
            "Replaying history for analogues "
            "(minutes on the first scan, cached afterwards)"
        )
        base = self._analogue_base(self._analogue_sample(prices, scan, holdings))

        unusual = [
            anomaly
            for anomaly in scan.anomalies
            if abs(anomaly.z_score) > self._entry
        ]

        liquidity = self._liquidity(prices)

        def tradable(anomaly) -> float:
            legs = (anomaly.ticker, anomaly.related_tickers[0])

            return min(liquidity.get(leg, 0.0) for leg in legs)

        # Reading the news and asking the model costs seconds
        # per candidate, and a universe of a thousand names has
        # hundreds of stretched pairs on any day. Liquidity is
        # free, so it is applied first, and only the most
        # stretched of what is tradable are read in depth.
        tradable_now = [
            anomaly
            for anomaly in unusual
            if tradable(anomaly) >= self._min_liquidity_musd
        ]

        shortlist = sorted(
            tradable_now,
            key=lambda anomaly: abs(anomaly.z_score),
            reverse=True,
        )[:MAX_CANDIDATES]

        self._stage(
            f"Reading the news behind the {len(shortlist)} most stretched "
            f"of {len(unusual)} unusual relationships"
        )

        setups = []
        admissible: dict[str, list[NewsItem]] = {}

        for anomaly in shortlist:
            a, b = anomaly.ticker, anomaly.related_tickers[0]
            relationship = relationship_of(scan, a, b)

            if relationship is None:
                continue

            # A above equilibrium: A is rich, B is cheap.
            long, short = (b, a) if anomaly.z_score > 0 else (a, b)
            outcome = base.outcome(anomaly.z_score)

            # Relevance-ranked, all published before the cutoff.
            admissible[anomaly.anomaly_id] = self._news.around(anomaly).admissible

            setups.append(
                Setup(
                    anomaly=anomaly,
                    long=long,
                    short=short,
                    z_score=anomaly.z_score,
                    relationship=relationship,
                    outcome=outcome,
                    expected_horizon=self._horizon(relationship.half_life_days),
                    headlines=self._headlines(
                        anomaly, admissible[anomaly.anomaly_id]
                    ),
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

        # Nemotron reads the headlines behind every candidate.
        # A lasting, company-specific event means the gap is a
        # repricing, not a dislocation, and the candidate goes.
        self._stage(f"Nemotron is reading {len(liquid)} candidates")
        triage_detail = self._triage(liquid, admissible)

        self._stage("Ranking")

        repriced = [
            s
            for s in liquid
            if s.triage is not None
            and s.triage.verdict == TriageVerdict.LASTING_EVENT.value
        ]

        dislocations = [s for s in liquid if s not in repriced]

        favourable = [
            s
            for s in dislocations
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
                FunnelStep(label="unusual today", count=len(unusual)),
                FunnelStep(label="liquid enough", count=len(tradable_now)),
                FunnelStep(
                    label="most stretched, read in depth",
                    count=len(liquid),
                    detail=(
                        f"the {MAX_CANDIDATES} largest deviations"
                        if len(tradable_now) > MAX_CANDIDATES
                        else None
                    ),
                ),
                FunnelStep(
                    label="dislocation, not a justified repricing",
                    count=len(dislocations),
                    detail=triage_detail,
                ),
                FunnelStep(
                    label="favourable in historical analogues",
                    count=len(favourable),
                ),
                FunnelStep(label="new to you", count=len(new)),
            ],
            setups=new,
            on_your_desk=[setup for setup in favourable if held(setup)],
            repriced=repriced,
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

    # -------------------------------------------------
    # Causal triage
    # -------------------------------------------------

    def _triage(
        self,
        setups: list[Setup],
        admissible: dict[str, list[NewsItem]],
    ) -> str:
        """
        Attach a TriageView to every setup that can get one and
        describe, for the funnel, what the model did.

        Stored readings are replayed without a model. Only the
        missing ones need it, and if it is offline they stay
        unread: nothing is dropped on a guess.
        """

        if self._llm_factory is None or self._triage_store is None:
            return "Causal triage is not configured."

        pending = []

        for setup in setups:
            offered = admissible[setup.anomaly.anomaly_id][:MAX_HEADLINES]
            key = self._triage_key(setup.anomaly.anomaly_id, offered)

            stored = self._triage_store.get(key)

            if stored is not None:
                setup.triage = self._view(stored, offered)
            else:
                pending.append((setup, offered, key))

        rejected = 0
        unreachable = 0

        if pending and self._llm_available():
            llm = self._llm_factory()

            with ThreadPoolExecutor(
                max_workers=min(self._llm_workers, len(pending)),
            ) as pool:
                results = pool.map(
                    lambda item: self._read(llm, *item),
                    pending,
                )

                for (setup, offered, _), stored in zip(pending, results):
                    if isinstance(stored, StoredTriage):
                        setup.triage = self._view(stored, offered)
                    elif stored == "unreachable":
                        unreachable += 1
                    else:
                        rejected += 1

        read = [s for s in setups if s.triage is not None]
        unread = len(setups) - len(read) - rejected - unreachable

        if not read and unread:
            return "Nemotron is offline: no candidate was read, none dropped."

        verdicts = Counter(s.triage.verdict for s in read)
        lasting = verdicts[TriageVerdict.LASTING_EVENT.value]

        detail = (
            f"Nemotron read {len(read)}: "
            f"{lasting} lasting event{'' if lasting == 1 else 's'} dropped, "
            f"{verdicts[TriageVerdict.TRANSIENT_EVENT.value]} transient, "
            f"{verdicts[TriageVerdict.NO_EVENT.value]} unexplained"
        )

        if rejected:
            detail += f"; {rejected} answers rejected by verification and kept unread"

        if unreachable:
            detail += (
                f"; {unreachable} not read (the model did not answer). "
                "Scan again to read them"
            )

        if unread:
            detail += f"; {unread} unread (model offline)"

        return detail + "."

    def _read(
        self,
        llm: StructuredLLM,
        setup: Setup,
        offered: list[NewsItem],
        key: str,
    ) -> StoredTriage | str:
        event = self._anomalies.event(setup.anomaly.anomaly_id)

        if event is None:
            return "rejected"

        headlines = tuple(
            TriageHeadline(
                headline_id=f"N{number}",
                ticker=item.ticker,
                title=item.title,
                summary=item.summary,
                publisher=item.publisher,
                published_at=item.published_at,
            )
            for number, item in enumerate(offered, start=1)
        )

        try:
            run, triage = triage_anomaly(event, headlines, llm)
        except LLMTransportError:
            # An outage says nothing about the candidate.
            return "unreachable"
        except Exception:
            # A malformed or unverifiable answer is not a
            # verdict. The candidate simply stays unread.
            return "rejected"

        cited = (
            offered[int(triage.headline_id[1:]) - 1].news_id
            if triage.headline_id
            else None
        )

        return self._triage_store.save(
            StoredTriage(
                key=key,
                anomaly_id=setup.anomaly.anomaly_id,
                verdict=triage.verdict.value,
                why_now=triage.why_now,
                headline_news_id=cited,
                model=run.model,
                created_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def _view(stored: StoredTriage, offered: list[NewsItem]) -> TriageView:
        return TriageView(
            verdict=stored.verdict,
            why_now=stored.why_now,
            headline=next(
                (i for i in offered if i.news_id == stored.headline_news_id),
                None,
            ),
            model=stored.model,
        )

    @staticmethod
    def _triage_key(anomaly_id: str, offered: list[NewsItem]) -> str:
        return sha1(
            json.dumps(
                [anomaly_id, PROMPT_VERSION, [item.news_id for item in offered]]
            ).encode()
        ).hexdigest()[:16]

    # -------------------------------------------------

    def _headlines(self, anomaly, items: list[NewsItem]) -> int:
        """
        Headlines naming either company before the evidence
        cutoff: whether there is anything to explain the move.
        """

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
        )

        if closes.shape[1] > LARGE_UNIVERSE:
            # Exchanges with different holidays share no
            # complete calendar: correlate pairwise instead.
            closes = closes.where(closes > 0)
            correlations = np.log(closes).diff().corr(
                min_periods=int(len(closes) * 0.9)
            )
        else:
            closes = closes.dropna(axis=1)
            correlations = np.log(closes).diff().corr()

        # The same admission rule the scan applies: a looser
        # bar inside a sector, the strict one across sectors.
        sector = pd.Series(self._instruments.sectors).reindex(correlations.index)
        codes = sector.to_numpy()

        same_sector = (codes[:, None] == codes[None, :]) & sector.notna().to_numpy()[:, None]

        required = np.where(
            same_sector & (self._corr_min_same_sector is not None),
            self._corr_min_same_sector or self._corr_min,
            self._corr_min,
        )

        upper = np.triu_indices_from(required, k=1)

        return int((correlations.to_numpy()[upper] >= required[upper]).sum())

    @staticmethod
    def _analogue_sample(prices: pd.DataFrame, scan, holdings: set[str]) -> pd.DataFrame:
        """
        The walk-forward record refits every relationship at
        fifty past dates. Over thousands of names that is days
        of compute, so for a large universe it is built from
        the book and the securities that are related TODAY,
        strongest relationships first: the analogues are then
        breaks of the kind of relationship being ranked.
        """

        if prices["ticker"].nunique() <= LARGE_UNIVERSE:
            return prices

        sample: dict[str, None] = dict.fromkeys(sorted(holdings))

        for fit in sorted(scan.fits, key=lambda f: f.pvalue):
            if len(sample) >= ANALOGUE_MAX_TICKERS:
                break

            sample.setdefault(fit.ticker_a)
            sample.setdefault(fit.ticker_b)

        return prices.loc[prices["ticker"].isin(sample)]

    def _analogue_base(self, prices: pd.DataFrame) -> PairAnalogueBase:
        """
        The walk-forward record takes minutes to build for a
        large universe, so it is kept on disk and reused while
        it is still current.

        "Current" is judged against the latest session the desk
        can see, which also keeps a replay honest: a record
        built for a later date contains breaks from the replayed
        desk's future and is rebuilt rather than reused.
        """

        latest = pd.to_datetime(prices["date"]).max().date()

        key = sha1(
            json.dumps(
                [
                    sorted(prices["ticker"].unique()),
                    self._formation_observations,
                    self._corr_min,
                    self._corr_min_same_sector,
                    self._alpha,
                    self._entry,
                ]
            ).encode()
        ).hexdigest()[:12]

        path = self._cache_dir / f"pairs-{key}.json"

        with self._lock:
            if path.is_file():
                base = PairAnalogueBase.model_validate_json(path.read_text())

                if self._is_current(base, latest):
                    return base

            base = self._build_analogues(
                prices,
                formation_observations=self._formation_observations,
                corr_min=self._corr_min,
                alpha=self._alpha,
                entry=self._entry,
                sectors=self._instruments.sectors,
                corr_min_same_sector=self._corr_min_same_sector,
                # Fifty refits of a hundred-odd names: the
                # batched engine turns minutes into seconds.
                **(
                    {"batched": True}
                    if prices["ticker"].nunique() > BATCHED_ABOVE
                    else {}
                ),
            )

            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(base.model_dump_json())

            return base

    @staticmethod
    def _is_current(base: PairAnalogueBase, latest) -> bool:
        if base.last_as_of is None:
            return False

        age = (latest - base.last_as_of).days

        # Younger than MIN: its last outcomes lie beyond
        # `latest`, i.e. it was built for a later date.
        # Older than MAX: weeks of recent breaks are missing.
        return ANALOGUE_MIN_AGE_DAYS <= age <= ANALOGUE_MAX_AGE_DAYS
