"""
From the wire to the graph: every article about the book that
has not been read yet is read and recorded. Resumable, and
safe to run in a loop.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from financial_assistant.api.models import NewsItem
from financial_assistant.llm.provider import StructuredLLM

from .extraction import PROMPT_VERSION, read_articles
from .resolution import Resolver
from .store import NewsGraphStore


def one_per_story(items: Iterable[NewsItem]) -> list[NewsItem]:
    """
    The same story from two providers, or syndicated under two
    URLs, is read once. The key is the normalised title per
    ticker and day: cheap, and wrong only for two different
    stories with an identical headline on the same day.
    """

    seen: set[tuple[str, str, str]] = set()
    kept = []

    for item in sorted(items, key=lambda i: i.published_at):
        key = (item.ticker.upper(), item.published_at.date().isoformat(), " ".join(item.title.lower().split()))

        if key in seen:
            continue

        seen.add(key)
        kept.append(item)

    return kept


def ingest(
    items: Iterable[NewsItem],
    *,
    store: NewsGraphStore,
    provider: StructuredLLM,
    resolver: Resolver,
    workers: int = 8,
    limit: int | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> dict:
    """
    Read what is new and record it. Returns counts.
    """

    done = store.extracted()
    todo = [item for item in one_per_story(items) if (item.news_id, item.ticker.upper()) not in done]

    if limit is not None:
        todo = todo[:limit]

    model = f"{provider.provider_name}/{provider.model_name}"
    read = failed = 0

    for index, reading in enumerate(read_articles(todo, provider, resolver, workers=workers), 1):
        item = todo[index - 1]

        store.record(
            article_id=reading.article_id,
            ticker=reading.ticker.upper(),
            published_at=item.published_at,
            model=model,
            prompt=PROMPT_VERSION,
            payload=reading.extraction.model_dump(mode="json") if reading.extraction else None,
            error=reading.error,
            nodes=reading.nodes,
            edges=reading.edges,
        )

        if reading.error:
            failed += 1
        else:
            read += 1

        if on_progress and (index % 50 == 0 or index == len(todo)):
            on_progress(f"{index}/{len(todo)} read, {failed} failed")

    return {"candidates": len(todo), "read": read, "failed": failed, "skipped": len(done)}


def articles_of(
    archive_read: Callable[..., Iterable[NewsItem]],
    tickers: Iterable[str],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[NewsItem]:
    items: list[NewsItem] = []

    for ticker in tickers:
        items.extend(archive_read(ticker, start=start, end=end))

    return items
