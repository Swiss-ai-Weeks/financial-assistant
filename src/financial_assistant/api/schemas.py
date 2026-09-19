"""Request and response bodies of the HTTP API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

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


class AnomalyNews(BaseModel):
    """
    News split by the evidence cutoff. Only `admissible`
    items may explain the anomaly; `hindsight` items were
    published after it became observable.
    """

    anomaly_id: str
    cutoff: str
    admissible: list[NewsItem]
    hindsight: list[NewsItem]


class StartInvestigationRequest(BaseModel):
    anomaly_id: str = Field(min_length=1)
    ticker: str | None = None


class ServiceStatus(BaseModel):
    name: str
    online: bool
    detail: str = ""


class SystemStatus(BaseModel):
    llm: ServiceStatus
    model: str
    provider: str
    news_sources: list[str]
    search: ServiceStatus
