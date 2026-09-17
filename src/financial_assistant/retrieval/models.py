from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
)

from financial_assistant.domain import (
    SourceDocument,
)


class RetrievalStatus(StrEnum):
    FETCHED = "fetched"
    REUSED = "reused"
    FILTERED_FUTURE = "filtered_future"
    FAILED = "failed"


class SearchHit(BaseModel):
    """
    Metadata returned by a search provider.

    A search hit is NOT yet evidence. It becomes a
    SourceDocument only after retrieval/extraction.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    hit_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)

    provider: str = Field(min_length=1)
    query: str = Field(min_length=1)

    rank: int = Field(ge=1)

    title: str = Field(min_length=1)
    url: HttpUrl

    snippet: str = ""

    publisher: str | None = None
    published_at: datetime | None = None


class RetrievalRecord(BaseModel):
    """
    Execution provenance for one attempted retrieval.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    record_id: str = Field(min_length=1)

    task_id: str = Field(min_length=1)
    hit_id: str = Field(min_length=1)

    provider: str = Field(min_length=1)
    query: str = Field(min_length=1)

    retrieved_at: datetime

    status: RetrievalStatus

    document_id: str | None = None
    note: str | None = None


class RetrievalBundle(BaseModel):
    """
    Result of executing a ResearchPlan.

    hits:
        what search returned

    documents:
        material actually retrieved

    records:
        what the system did with each hit
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    plan_id: str = Field(min_length=1)
    as_of: datetime

    hits: tuple[SearchHit, ...] = ()

    documents: tuple[
        SourceDocument,
        ...
    ] = ()

    records: tuple[
        RetrievalRecord,
        ...
    ] = ()
