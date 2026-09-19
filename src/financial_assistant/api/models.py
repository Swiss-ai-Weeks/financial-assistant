"""
Objects the desk stores and serves.

They are separate from the analytical domain models in
financial_assistant.domain, which describe evidence and
must stay independent from how the desk presents it.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from financial_assistant.anomaly_detection import StrategyKind


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str
    exchange: str | None = None
    kind: str | None = None
    sector: str | None = None


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str = Field(min_length=1)
    name: str = ""
    shares: float = Field(gt=0)
    added_at: datetime | None = None


class Portfolio(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "Portfolio"
    manager: str = ""
    positions: tuple[Position, ...] = ()

    @property
    def tickers(self) -> tuple[str, ...]:
        return tuple(position.ticker for position in self.positions)


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    news_id: str
    ticker: str
    title: str
    url: str
    publisher: str | None = None
    published_at: datetime
    summary: str = ""
    provider: str


class Anomaly(BaseModel):
    """
    One row of the anomaly blotter, whichever detector
    produced it.
    """

    model_config = ConfigDict(frozen=True)

    anomaly_id: str
    ticker: str
    related_tickers: tuple[str, ...] = ()

    strategy: StrategyKind
    kind: str

    observed_on: date
    z_score: float
    threshold: float
    severity: float = Field(ge=0.0, le=1.0)

    direction: str
    summary: str
    metrics: dict[str, float | int | str] = Field(default_factory=dict)


class InvestigationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestigationStage(BaseModel):
    key: str
    label: str
    status: StageStatus = StageStatus.PENDING
    detail: str = ""
    seconds: float | None = None


class HypothesisVerdict(BaseModel):
    hypothesis_id: str
    text: str
    supporting: int = 0
    contradicting: int = 0
    weakening: int = 0
    context: int = 0
    score: float = 0.0
    assumptions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()


class EvidenceClaim(BaseModel):
    claim_id: str
    text: str
    claim_type: str
    source_quote: str
    document_id: str
    document_title: str
    publisher: str | None = None
    url: str
    published_at: datetime | None = None


class Investigation(BaseModel):
    investigation_id: str
    anomaly: Anomaly
    status: InvestigationStatus = InvestigationStatus.QUEUED

    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None

    # News admitted as evidence must be published at or
    # before this instant.
    evidence_cutoff: datetime

    model: str
    provider: str

    stages: list[InvestigationStage] = Field(default_factory=list)

    hypotheses: list[HypothesisVerdict] = Field(default_factory=list)
    claims: list[EvidenceClaim] = Field(default_factory=list)

    documents_considered: int = 0
    documents_used: int = 0

    # ClaimGraph v0.2 payload rendered by the frontend.
    graph: dict[str, Any] | None = None
