from __future__ import annotations

import os
from datetime import datetime

import requests

from .models import SearchHit


class NewsApiSearchProvider:
    """
    SearchProvider backed by NewsAPI.

    NewsAPI is used for DISCOVERY only.

    Articles returned here are SearchHits, not
    epistemic evidence. The article URL must still
    be retrieved and normalized before claim
    extraction.
    """

    name = "newsapi"

    endpoint = (
        "https://newsapi.org/v2/everything"
    )

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.api_key = (
            api_key
            or os.getenv("NEWS_API_KEY")
        )

        if not self.api_key:
            raise ValueError(
                "NEWS_API_KEY is not configured"
            )

        self.timeout_seconds = (
            timeout_seconds
        )

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

        response = requests.get(
            self.endpoint,
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": min(
                    limit,
                    100,
                ),
                "apiKey": self.api_key,
            },
            timeout=self.timeout_seconds,
        )

        response.raise_for_status()

        payload = response.json()

        if payload.get("status") != "ok":
            raise RuntimeError(
                "NewsAPI returned an "
                f"unsuccessful response: {payload}"
            )

        hits: list[SearchHit] = []

        for rank, article in enumerate(
            payload.get("articles", []),
            start=1,
        ):
            url = article.get("url")
            title = article.get("title")

            if not url or not title:
                continue

            published_at = None

            raw_published_at = (
                article.get("publishedAt")
            )

            if raw_published_at:
                published_at = (
                    datetime.fromisoformat(
                        raw_published_at.replace(
                            "Z",
                            "+00:00",
                        )
                    )
                )

            source = (
                article.get("source")
                or {}
            )

            hits.append(
                SearchHit(
                    hit_id=(
                        f"{task_id}:newsapi:"
                        f"{rank}"
                    ),

                    task_id=task_id,

                    provider=self.name,
                    query=query,
                    rank=rank,

                    title=title,
                    url=url,

                    snippet=(
                        article.get(
                            "description"
                        )
                        or ""
                    ),

                    publisher=(
                        source.get("name")
                    ),

                    published_at=(
                        published_at
                    ),
                )
            )

        return tuple(hits)
