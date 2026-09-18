from __future__ import annotations

from datetime import (
    date,
    datetime,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class MarketDataManifest(BaseModel):
    """
    Provenance accompanying one downloaded market-data
    snapshot.

    The statistical detector consumes the price rows.
    The manifest records where those observations came
    from and how they were transformed.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    provider: str = Field(
        min_length=1
    )

    interval: str = Field(
        min_length=1
    )

    requested_start: date
    requested_end: date

    retrieved_at: datetime

    tickers: tuple[str, ...]

    auto_adjust: bool

    row_count: int = Field(
        ge=0
    )
