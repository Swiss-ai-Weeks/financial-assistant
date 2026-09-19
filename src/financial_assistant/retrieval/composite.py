from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from financial_assistant.domain import SourceDocument

from .interfaces import (
    DocumentFetcher,
    SearchProvider,
)

from .models import SearchHit


class CompositeSearchProvider:
    """
    Query multiple discovery systems for the same
    research task.

    Each underlying SearchHit retains its own provider
    identity, e.g. "bookreader" or "searxng".

    Results are interleaved rather than treating ranks
    from unrelated retrieval systems as comparable.
    """

    name = "composite"

    def __init__(
        self,
        providers: Sequence[SearchProvider],
    ):
        if not providers:
            raise ValueError(
                "At least one search provider is required"
            )

        self.providers = tuple(providers)

    def search(
        self,
        query: str,
        *,
        task_id: str,
        limit: int = 5,
        as_of: datetime | None = None,
    ) -> tuple[SearchHit, ...]:
        if limit < 1:
            raise ValueError(
                "limit must be >= 1"
            )

        provider_hits: list[
            tuple[SearchHit, ...]
        ] = []

        # Deliberately sequential for now:
        # controlled corpus first, open web second.
        for provider in self.providers:
            hits = provider.search(
                query,
                task_id=task_id,
                limit=limit,
                as_of=as_of,
            )

            provider_hits.append(hits)

        merged: list[SearchHit] = []

        # Round-robin prevents either retrieval source
        # from completely dominating the candidate set.
        position = 0

        while len(merged) < limit:
            added = False

            for hits in provider_hits:
                if position >= len(hits):
                    continue

                hit = hits[position]

                # This is the composite ordering, not an
                # assertion that BM25 and web-search ranks
                # are directly comparable.
                hit = hit.model_copy(
                    update={
                        "rank": len(merged) + 1,
                    }
                )

                merged.append(hit)
                added = True

                if len(merged) >= limit:
                    break

            if not added:
                break

            position += 1

        return tuple(merged)


class DispatchingDocumentFetcher:
    """
    Send each SearchHit to the fetcher appropriate for
    the provider that discovered it.
    """

    name = "dispatch"

    def __init__(
        self,
        fetchers: Mapping[
            str,
            DocumentFetcher,
        ],
    ):
        self.fetchers = dict(fetchers)

    def fetch(
        self,
        hit: SearchHit,
        *,
        retrieved_at: datetime,
    ) -> SourceDocument:
        try:
            fetcher = self.fetchers[
                hit.provider
            ]

        except KeyError as exc:
            raise ValueError(
                "No document fetcher configured "
                f"for provider {hit.provider!r}"
            ) from exc

        return fetcher.fetch(
            hit,
            retrieved_at=retrieved_at,
        )
