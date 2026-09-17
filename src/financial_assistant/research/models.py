from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class ResearchTaskKind(StrEnum):
    """
    Semantic information requirements.

    These are intentionally not tied to a particular
    search engine or API.
    """

    RECENT_NEWS = "recent_news"
    UPCOMING_EVENTS = "upcoming_events"
    PRIMARY_DISCLOSURES = "primary_disclosures"
    SHARED_CONTEXT = "shared_context"


class ResearchSourceClass(StrEnum):
    """
    Preferred source classes.

    Retrieval adapters will later decide how each
    source class is actually queried.
    """

    NEWS = "news"
    COMPANY_IR = "company_ir"
    SEC_EDGAR = "sec_edgar"
    CALENDAR = "calendar"
    MARKET_CONTEXT = "market_context"


class ResearchTask(BaseModel):
    """
    One explicit information requirement created from
    an anomaly.

    A ResearchTask says what we need to know.
    It does not yet contain search-engine-specific
    implementation details.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    task_id: str = Field(min_length=1)

    kind: ResearchTaskKind

    # One or more securities/entities relevant to
    # this information requirement.
    entities: tuple[str, ...]

    question: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    source_preferences: tuple[
        ResearchSourceClass,
        ...
    ]

    # Time bounds are hints to the later retrieval
    # layer, not hard-coded search syntax.
    lookback_days: int | None = Field(
        default=None,
        ge=1,
    )

    forward_days: int | None = Field(
        default=None,
        ge=1,
    )

    # 1 = highest priority.
    priority: int = Field(
        default=3,
        ge=1,
        le=5,
    )


class ResearchPlan(BaseModel):
    """
    Deterministic investigation plan produced from one
    anomaly.

    `as_of` is inherited from the anomaly timestamp so
    historical analysis remains point-in-time safe.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    plan_id: str = Field(min_length=1)

    anomaly_id: str = Field(min_length=1)
    as_of: datetime

    tasks: tuple[
        ResearchTask,
        ...
    ]
