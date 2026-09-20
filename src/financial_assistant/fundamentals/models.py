"""Point-in-time records. Filing dates and retrieval times are distinct clocks."""
from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class FinancialFact(Record):
    fact_id: str
    ticker: str
    cik: str
    issuer: str
    concept: str
    taxonomy: str = 'us-gaap'
    tag: str
    value: float
    unit: str
    period_start: date | None = None
    period_end: date
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str
    filed_at: date
    available_at: datetime
    accession: str
    frame: str | None = None
    provider: str = 'SEC EDGAR'
    retrieved_at: datetime


class MetricResult(Record):
    calculation_id: str
    metric_id: str
    display_name: str
    formula_version: str
    formula: str
    required_inputs: tuple[str, ...] = ()
    period_end: date
    frequency: str
    value: float | None = None
    unit: str
    input_ids: tuple[str, ...] = ()
    input_fact_ids: tuple[str, ...] = ()
    available_at: datetime | None = None
    status: Literal['available', 'unavailable', 'not_applicable'] = 'available'
    unavailable_reason: str | None = None
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class FundamentalEvidenceBundle(Record):
    ticker: str
    issuer: str = ''
    cik: str = ''
    as_of: datetime
    periods: tuple[date, ...] = ()
    frequency: str = 'annual'
    facts: tuple[FinancialFact, ...] = ()
    calculations: tuple[MetricResult, ...] = ()
    warnings: tuple[str, ...] = ()
    status: str = 'available'
    retrieved_at: datetime
    provider_execution_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(Record):
    ticker: str
    cik: str
    facts: dict[str, Any]
    submissions: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
