from __future__ import annotations

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class PairFit(BaseModel):
    """
    Frozen statistical relationship estimated only
    from the formation window.

    These parameters must not be recomputed using the
    later monitoring window.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    ticker_a: str = Field(min_length=1)
    ticker_b: str = Field(min_length=1)

    metric: str = "close"

    formation_start: date
    formation_end: date

    correlation: float

    const: float
    beta: float

    adf_stat: float
    pvalue: float

    adf_lags: int
    nobs: int

    half_life_days: float | None = None

    # Distribution of the formation-period spread.
    spread_mean: float
    spread_std: float = Field(gt=0)


class PairAnomaly(BaseModel):
    """
    Point-in-time deviation from a previously fitted
    pair relationship.

    This is an attention event, not an investment
    recommendation and not a causal conclusion.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    anomaly_id: str = Field(min_length=1)

    ticker_a: str = Field(min_length=1)
    ticker_b: str = Field(min_length=1)

    metric: str

    monitoring_start: date
    monitoring_end: date

    first_flag: date

    threshold: float = Field(gt=0)

    n_days_flagged: int = Field(gt=0)

    z_score: float
    max_abs_z: float

    # Neutral description of relative deviation.
    relative_direction: str

    # Preserve the frozen formation parameters used.
    beta: float
    const: float

    formation_start: date
    formation_end: date
