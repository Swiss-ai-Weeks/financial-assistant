from __future__ import annotations

from datetime import datetime
from hashlib import sha1
from pathlib import Path

from financial_assistant.domain import SourceDocument
from financial_assistant.retrieval import DocumentFetcher, SearchHit


class CachedDocumentFetcher:
    """
    Read-through cache in front of a DocumentFetcher.

    The first investigation that needs an article fetches
    it; every later one replays the stored copy. Pages
    change, get paywalled and disappear, so without this
    the same anomaly could be explained differently on
    demo day than it was in rehearsal.

    Article text is third-party content: the cache lives
    under data/cache, which is not committed.
    """

    def __init__(self, fetcher: DocumentFetcher, directory: Path):
        self._fetcher = fetcher
        self._directory = directory
        self.name = f"cached-{fetcher.name}"

    def fetch(self, hit: SearchHit, *, retrieved_at: datetime) -> SourceDocument:
        path = self._directory / (
            sha1(str(hit.url).encode("utf-8")).hexdigest()[:16] + ".json"
        )

        if path.is_file():
            return SourceDocument.model_validate_json(path.read_text())

        document = self._fetcher.fetch(hit, retrieved_at=retrieved_at)

        self._directory.mkdir(parents=True, exist_ok=True)
        path.write_text(document.model_dump_json(indent=1))

        return document
