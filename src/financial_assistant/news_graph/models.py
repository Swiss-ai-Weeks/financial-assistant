from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    """
    What kind of thing an article reports. The vocabulary is
    deliberately small: every type must mean something to a
    trader and be recognisable from a headline and a summary.
    """

    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    M_AND_A = "m_and_a"
    REGULATION = "regulation"
    LITIGATION = "litigation"
    SUPPLY_CHAIN = "supply_chain"
    CUSTOMER = "customer"
    PRODUCT = "product"
    MANAGEMENT = "management"
    CAPITAL = "capital"
    ANALYST = "analyst"
    MACRO = "macro"
    MARKET_COMMENTARY = "market_commentary"
    OTHER = "other"


EVENT_TYPES = tuple(EventType)


class EntityKind(StrEnum):
    COMPANY = "company"
    PERSON = "person"
    REGULATOR = "regulator"
    PRODUCT = "product"
    PLACE = "place"
    OTHER = "other"


class Direction(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class Materiality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=80)
    kind: EntityKind


class Extraction(BaseModel):
    """
    What the model reads out of one article. `event` is the
    canonical label of what happened, short enough that two
    articles about the same thing produce the same words.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: EventType
    event: str | None = Field(default=None, max_length=90)
    entities: tuple[ExtractedEntity, ...] = Field(default=(), max_length=8)
    direction: Direction = Direction.NEUTRAL
    materiality: Materiality = Materiality.LOW


class NodeKind(StrEnum):
    SECURITY = "security"
    ENTITY = "entity"
    EVENT = "event"
    EVENT_TYPE = "event_type"
    ARTICLE = "article"


@dataclass(frozen=True)
class Node:
    node_id: str
    kind: NodeKind
    label: str
    props: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    """
    One timestamped interaction. `t` is when the world could
    know it (the article's publication); `article_id` is the
    provenance every edge must resolve to.
    """

    src: str
    dst: str
    kind: str
    t: datetime
    article_id: str
    props: dict = field(default_factory=dict)
