from __future__ import annotations

from datetime import datetime
from typing import Protocol

from financial_assistant.domain import (
    SourceDocument,
)

from .models import SearchHit


class SearchProvider(Protocol):
    """
    Something capable of turning a query into search
    results.

    Later implementations might be:
      - SearXNG
      - a commercial search API
      - an internal news index
    """

    name: str

    def search(
        self,
        query: str,
        *,
        task_id: str,
        limit: int = 5,
        as_of: datetime | None = None,
    ) -> tuple[SearchHit, ...]:
        ...


class DocumentFetcher(Protocol):
    """
    Something capable of turning a SearchHit into a
    normalized SourceDocument.

    Later this may use:
      HTTP
        ↓
      Trafilatura
        ↓
      Playwright fallback
    """

    name: str

    def fetch(
        self,
        hit: SearchHit,
        *,
        retrieved_at: datetime,
    ) -> SourceDocument:
        ...
