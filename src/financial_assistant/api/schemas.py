"""Request and response bodies of the HTTP API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from financial_assistant.analytics import (
    AnalogueOutcome,
    HorizonReading,
    PeerReading,
)
from financial_assistant.api.models import Anomaly, NewsItem


class Quote(BaseModel):
    ticker: str
    as_of: date
    last: float
    previous_close: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: float
    month_return_pct: float


class Candle(BaseModel):
    time: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    ma_fast: float | None = None
    ma_slow: float | None = None
    vwap: float | None = None
    twap: float | None = None


class CandleSeries(BaseModel):
    ticker: str
    fast: int
    slow: int
    vwap_window: int
    twap_window: int
    candles: list[Candle]


class ReviewWindow(BaseModel):
    start: date
    end: date
    days: int


class PositionView(BaseModel):
    ticker: str
    name: str
    shares: float
    last: float
    market_value: float
    weight_pct: float
    day_change_pct: float
    month_return_pct: float
    contribution_pct: float
    anomaly_count: int


class PortfolioView(BaseModel):
    name: str
    manager: str
    window: ReviewWindow
    benchmark: str
    market_value: float
    day_change_pct: float
    month_return_pct: float
    benchmark_return_pct: float
    active_return_pct: float
    positions: list[PositionView]


class AddPositionRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    shares: float = Field(default=100, gt=0)


class WeightedPosition(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    weight: float = Field(ge=0.0, le=1.0)


class SetWeightsRequest(BaseModel):
    """
    The book stated as target weights. They are turned into
    share counts at the latest visible close, because every
    money figure on the desk (impact, hedges) is in shares.
    """

    name: str | None = None
    notional: float = Field(default=1_000_000, gt=0)
    positions: list[WeightedPosition] = Field(min_length=1, max_length=100)


class SimulateOverlayRequest(BaseModel):
    ticker_a: str = Field(min_length=1, max_length=12)
    ticker_b: str = Field(min_length=1, max_length=12)
    gross_overlay: float = Field(default=0.02, ge=0.0, le=1.0)
    lookback: int = Field(default=252, ge=20, le=252)


class MarketContextRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=4)


class PairFitView(BaseModel):
    ticker_a: str
    ticker_b: str
    correlation: float
    beta: float
    pvalue: float
    half_life_days: float | None
    z_score: float | None
    flagged: bool


class PairScan(BaseModel):
    focus: list[str]
    universe_size: int
    formation_start: date
    formation_end: date
    monitoring_start: date
    monitoring_end: date
    entry: float
    fits: list[PairFitView]
    anomalies: list[Anomaly]


class AddPositionResponse(BaseModel):
    portfolio: PortfolioView
    pair_scan: PairScan


class SpreadPoint(BaseModel):
    time: date
    z_score: float


class PairSpread(BaseModel):
    ticker_a: str
    ticker_b: str
    beta: float
    entry: float
    formation_end: date
    points: list[SpreadPoint]


class StrategyCard(BaseModel):
    key: str
    category: str
    name: str
    description: str
    assumption: str
    detects: str
    anomaly_count: int


class KeyDate(BaseModel):
    label: str
    day: date


class AnomalyNews(BaseModel):
    """
    News split by the evidence cutoff. Only `admissible`
    items may explain the anomaly; `hindsight` items were
    published after it became observable.
    """

    anomaly_id: str
    cutoff: str

    # The moments an explanation is most likely dated near.
    # `admissible` leads with articles from around each.
    key_dates: list[KeyDate] = []

    admissible: list[NewsItem]
    hindsight: list[NewsItem]


class NewsSourceStatus(BaseModel):
    """
    One news source as the desk sees it. A source without a
    key is listed too, as not configured, so the UI can say
    what is missing. Errors are messages only: no URL, no key.
    """

    name: str
    configured: bool
    local: bool = False

    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_error: str | None = None

    # Free tiers are counted per day. None: no daily cap.
    requests_today: int = 0
    daily_budget: int | None = None
    min_refresh_minutes: int | None = None

    # Articles this source was the first to bring in.
    articles: int = 0


class StartInvestigationRequest(BaseModel):
    anomaly_id: str = Field(min_length=1)
    ticker: str | None = None

    # Which configured model explains it. Unset: the default.
    model_id: str | None = None


class StartFollowUpRequest(BaseModel):
    requirement_id: str = Field(min_length=1)
    model_id: str | None = None


class ModelView(BaseModel):
    """One configured model as the browser may see it: no URL, no key."""

    id: str
    label: str
    origin: str = ""
    provider: str
    model: str
    local: bool
    roles: list[str]
    default: bool = False
    online: bool = False
    detail: str = ""


class ModelList(BaseModel):
    default_id: str
    egress_policy: str
    models: list[ModelView]


class ServiceStatus(BaseModel):
    name: str
    online: bool
    detail: str = ""


class TimeTravelRequest(BaseModel):
    # None returns the desk to the present.
    as_of: date | None = None


class SystemStatus(BaseModel):
    as_of: date | None
    llm: ServiceStatus
    llm_local: bool
    model: str
    provider: str
    news_sources: list[str]
    search: ServiceStatus


# -----------------------------------------------------
# Story 1 · post-mortem
# -----------------------------------------------------


class Relationship(BaseModel):
    """Why two securities are treated as related."""

    ticker_a: str
    ticker_b: str
    correlation: float
    beta: float
    pvalue: float
    half_life_days: float | None
    formation_start: date
    formation_end: date


class Finding(BaseModel):
    """
    One thing the manager missed: what diverged, what it
    cost, when it became visible, and why it happened.
    """

    anomaly: Anomaly
    headline: str
    statement: str

    impact: float
    impact_since: date
    hedged_impact: float | None = None

    signal_date: date
    sessions_of_warning: int
    missed_signal: str

    relationship: Relationship | None = None

    explanation: str | None = None
    confidence: str | None = None
    investigation_id: str | None = None


class PostMortem(BaseModel):
    window: ReviewWindow
    currency: str
    total_impact: float
    findings: list[Finding]


# -----------------------------------------------------
# Story 2 · copilot
# -----------------------------------------------------


class HorizonTick(BaseModel):
    horizon: str
    z_score: float | None
    unusual: bool
    available: bool


class MatrixRow(BaseModel):
    """
    One security read at every horizon. Side by side with
    its peers it shows at a glance whether a move is the
    stock's own or the group's, and at which timescale.
    """

    ticker: str
    is_subject: bool
    correlation: float | None = None
    ticks: list[HorizonTick]


class Microscope(BaseModel):
    ticker: str
    as_of: date
    horizon: str
    ticks: list[HorizonTick]
    reading: HorizonReading
    statements: list[str]
    peers: list[PeerReading]
    matrix: list[MatrixRow]
    outcome: AnalogueOutcome | None
    latest_anomaly: Anomaly | None


# -----------------------------------------------------
# Story 3 · discovery
# -----------------------------------------------------


class FunnelStep(BaseModel):
    label: str
    count: int
    detail: str | None = None


class TriageView(BaseModel):
    """
    Nemotron's first reading of one candidate: is there an
    event behind the move, and does it last.
    """

    verdict: str
    why_now: str
    headline: NewsItem | None = None
    model: str


class Setup(BaseModel):
    anomaly: Anomaly
    long: str
    short: str
    z_score: float
    relationship: Relationship
    outcome: AnalogueOutcome | None
    expected_horizon: str
    headlines: int
    liquidity_musd: float
    why_connected: list[str]
    invalidation: list[str]
    score: float
    triage: TriageView | None = None


class Discovery(BaseModel):
    as_of: date
    funnel: list[FunnelStep]

    # Relationships the manager is not already looking at.
    setups: list[Setup]

    # Setups that involve a holding. They are real, but the
    # post-mortem has already reported them: showing one as
    # "today's discovery" would present old news as new.
    on_your_desk: list[Setup]

    # Candidates the model read as a lasting, company-specific
    # event. The gap is then a repricing that should not be
    # expected to close, so they are dropped, in the open.
    repriced: list[Setup]
    analogue_breaks: int
    analogue_period: str


class DiscoveryJob(BaseModel):
    """
    State of the one discovery scan the desk runs at a time.

    A scan can take minutes (a first scan replays years of
    history), far longer than any proxy keeps a request open,
    so it runs in the background and is polled.
    """

    status: str = "idle"          # idle | running | completed | failed
    stage: str = ""
    started_at: str | None = None
    seconds: float | None = None
    error: str | None = None
    discovery: Discovery | None = None
