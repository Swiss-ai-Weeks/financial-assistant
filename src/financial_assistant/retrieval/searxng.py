from __future__ import annotations

import json
import os

from datetime import (
    datetime,
    timezone,
)

from hashlib import sha1

from urllib.parse import (
    urlencode,
    urlparse,
)

from urllib.request import (
    Request,
    urlopen,
)

from .models import SearchHit


class SearxngSearchProvider:
    """
    SearchProvider backed by our local SearXNG instance.

    SearXNG performs DISCOVERY only.

    A SearchHit is not yet epistemic evidence. The
    original URL must later be fetched and normalized
    into a SourceDocument.
    """

    name = "searxng"

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 20.0,
        language: str = "en",
    ):
        self.base_url = (
            base_url
            or os.getenv(
                "SEARXNG_URL",
                "http://127.0.0.1:8888",
            )
        ).rstrip("/")

        self.timeout_seconds = (
            timeout_seconds
        )

        self.language = language

    def search(
        self,
        query: str,
        *,
        task_id: str,
        limit: int = 5,
    ) -> tuple[SearchHit, ...]:
        if limit < 1:
            raise ValueError(
                "limit must be >= 1"
            )

        params = urlencode(
            {
                "q": query,
                "format": "json",
                "language": self.language,
            }
        )

        request = Request(
            f"{self.base_url}/search?{params}",
            headers={
                "User-Agent":
                    "ClaimGraph/0.2"
            },
        )

        with urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            payload = json.load(
                response
            )

        results = (
            payload.get("results")
            or []
        )

        hits: list[SearchHit] = []

        for rank, result in enumerate(
            results,
            start=1,
        ):
            if len(hits) >= limit:
                break

            url = result.get("url")
            title = result.get("title")

            if not url or not title:
                continue

            published_at = (
                _parse_published_date(
                    result.get(
                        "publishedDate"
                    )
                    or result.get(
                        "pubdate"
                    )
                )
            )

            parsed = urlparse(url)

            publisher = (
                parsed.hostname
                or "unknown"
            )

            digest = sha1(
                url.encode("utf-8")
            ).hexdigest()[:12]

            hits.append(
                SearchHit(
                    hit_id=(
                        f"{task_id}:"
                        f"searxng:{digest}"
                    ),

                    task_id=task_id,

                    provider=self.name,
                    query=query,

                    rank=rank,

                    title=title,
                    url=url,

                    snippet=(
                        result.get("content")
                        or ""
                    ),

                    publisher=publisher,

                    published_at=(
                        published_at
                    ),
                )
            )

        return tuple(hits)


def _parse_published_date(
    value: str | None,
) -> datetime | None:
    """
    Normalize SearXNG publication timestamps when
    available.

    Many search results do not expose one, in which
    case we preserve the uncertainty as None rather
    than inventing a timestamp.
    """

    if not value:
        return None

    normalized = (
        value
        .strip()
        .replace("Z", "+00:00")
    )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    except ValueError:
        return None
