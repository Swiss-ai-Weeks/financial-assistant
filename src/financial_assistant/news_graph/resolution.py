"""
Identity of nodes: which names are the same thing.

Conservative on purpose. Two mentions merge when their
normalised names match exactly, or when a name is a known
alias of a security of the book. Anything less certain stays
apart: a graph with two nodes for one company is a nuisance,
a graph that merges two companies into one is wrong.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .models import EntityKind, EventType

SUFFIXES = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|ltd|limited|plc|"
    r"holdings|holding|group|technologies|technology|the)\b\.?",
    re.IGNORECASE,
)

PUNCTUATION = re.compile(r"[^a-z0-9 ]+")


def normalise(name: str) -> str:
    text = name.lower().replace("&", " and ")
    text = SUFFIXES.sub(" ", text)
    text = PUNCTUATION.sub(" ", text)

    return " ".join(text.split())


class Resolver:
    """
    Maps names to node ids. Securities of the book are known
    by ticker and by company name (and its normalised form);
    everything else is an entity keyed by kind and name.
    """

    def __init__(self, securities: dict[str, str]):
        """`securities`: ticker -> company name."""

        self._aliases: dict[str, str] = {}

        for ticker, name in securities.items():
            symbol = ticker.upper()
            self._aliases[symbol.lower()] = symbol

            if name:
                self._aliases[normalise(name)] = symbol
                # "Applied Materials Inc" and "Applied Materials"
                # both normalise to the same thing; a bare first
                # word ("Micron") is too loose to add.

    def security(self, name: str) -> str | None:
        """The ticker a company name refers to, if it is in the book."""

        return self._aliases.get(normalise(name)) or self._aliases.get(name.strip().lower())

    @staticmethod
    def security_id(ticker: str) -> str:
        return f"security:{ticker.upper()}"

    def entity_id(self, name: str, kind: EntityKind) -> str | None:
        """
        A node id for an entity, or None when the name is empty
        after normalisation (a stray symbol, a number).
        """

        key = normalise(name)

        if not key:
            return None

        return f"entity:{kind.value}:{key}"

    @staticmethod
    def event_type_id(event_type: EventType) -> str:
        return f"event_type:{event_type.value}"

    @staticmethod
    def event_id(event_type: EventType, label: str, published_at: datetime) -> str | None:
        """
        A canonical event: the same label of the same type in
        the same ISO week. Coverage of one thing spans days;
        a week is the widest merge that stays safe.
        """

        key = normalise(label)

        if not key:
            return None

        return f"event:{event_type.value}:{key}:{week_of(published_at.date())}"


def week_of(day: date) -> str:
    monday = day - timedelta(days=day.weekday())

    return monday.isoformat()
