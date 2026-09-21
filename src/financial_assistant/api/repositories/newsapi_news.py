"""
NewsAPI /v2/everything as dated ticker news, live and for the
news archive.

The investigation pipeline also searches NewsAPI, through
retrieval.newsapi.NewsApiSearchProvider: free text, no dates,
hits to be fetched and read. This module asks a different
question of the same API: what was published about ONE company
between two instants. It therefore sends a date range, keeps
only full timestamps and drops what is not about the company.

The key goes in a header, not in the URL. Free tier: 100
requests a day, articles a day late, one month of history.
"""

from __future__ import annotations

from hashlib import sha1
from urllib.parse import urlencode

from financial_assistant.api.relevance import (
    company_aliases,
    company_phrase,
    relevance,
)

from .gdelt import FINANCE_TERMS
from .news_provider import KeyedNewsProvider


ENDPOINT = "https://newsapi.org/v2/everything"
MAX_ARTICLES = 100


def build_query(ticker: str, company: str) -> str:
    """
    Same reasoning as for GDELT: a text index is asked for
    the company's written name, narrowed to coverage an
    investor would read. A bare ticker only when no name
    is known.
    """

    phrase = company_phrase(ticker, company)
    subject = f'"{phrase}"' if " " in phrase else phrase

    return f"{subject} AND {FINANCE_TERMS}"


class NewsApiProvider(KeyedNewsProvider):
    name = "newsapi"
    key_variable = "NEWS_API_KEY"

    min_interval_seconds = 1.0

    min_refresh_minutes = 4 * 60
    daily_budget = 100

    # The developer plan answers a request for anything
    # older with an error instead of fewer results.
    max_history_days = 29

    def signature(self, ticker: str, company: str) -> str:
        query = build_query(ticker, company)

        return f"{self.version}-{sha1(query.encode()).hexdigest()[:8]}"

    def _request(self, ticker, company, start, end):
        params = urlencode(
            {
                "q": build_query(ticker, company),
                "from": f"{start:%Y-%m-%dT%H:%M:%S}",
                "to": f"{end:%Y-%m-%dT%H:%M:%S}",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": MAX_ARTICLES,
            }
        )

        return f"{ENDPOINT}?{params}", {"X-Api-Key": self._api_key}

    def _parse(self, payload):
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            payload = payload if isinstance(payload, dict) else {}

            raise self._refused(
                payload.get("message") or "unsuccessful response",
                rate_limited=payload.get("code") == "rateLimited",
            )

        return [
            {
                "title": row.get("title"),
                "url": row.get("url"),
                "published_at": row.get("publishedAt"),
                "publisher": (row.get("source") or {}).get("name"),
                "summary": row.get("description"),
            }
            for row in payload.get("articles", [])
            # What NewsAPI leaves behind when a publisher
            # withdraws an article.
            if row.get("title") != "[Removed]"
        ]

    def _keep(self, item, ticker, company):
        return relevance(item, company_aliases(ticker, company)) > 0
