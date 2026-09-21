"""
GNews search, live and for the news archive.

A general news index, not a financial one: it matches text,
knows nothing about tickers and tags nothing. It earns its
place by reading publishers the financial feeds do not, and
by accepting a time range. Free tier: 100 requests a day, a
handful of articles per request, about a month of history.
"""

from __future__ import annotations

from hashlib import sha1
from urllib.parse import urlencode

from financial_assistant.api.relevance import (
    company_aliases,
    company_phrase,
    relevance,
)

from .news_provider import KeyedNewsProvider


ENDPOINT = "https://gnews.io/api/v4/search"

# The plan decides how many actually come back.
MAX_ARTICLES = 25


def build_query(ticker: str, company: str) -> str:
    """
    The name a journalist would write, or the ticker.

    A suffixed symbol (NESN.SW) never appears in prose, so
    it is only searched when there is no name to search.
    """

    phrase = company_phrase(ticker, company)

    if phrase == ticker:
        return ticker

    return f'"{phrase}"' if "." in ticker else f'"{phrase}" OR {ticker}'


class GNewsProvider(KeyedNewsProvider):
    name = "gnews"
    key_variable = "GNEWS_API_KEY"

    # The free tier refuses more than one request a second.
    min_interval_seconds = 1.1

    min_refresh_minutes = 4 * 60
    daily_budget = 100

    def signature(self, ticker: str, company: str) -> str:
        query = build_query(ticker, company)

        return f"{self.version}-{sha1(query.encode()).hexdigest()[:8]}"

    def _request(self, ticker, company, start, end):
        params = urlencode(
            {
                "q": build_query(ticker, company),
                "lang": "en",
                "from": f"{start:%Y-%m-%dT%H:%M:%SZ}",
                "to": f"{end:%Y-%m-%dT%H:%M:%SZ}",
                "max": MAX_ARTICLES,
                "sortby": "publishedAt",
                "apikey": self._api_key,
            }
        )

        return f"{ENDPOINT}?{params}", {}

    def _parse(self, payload):
        if not isinstance(payload, dict) or "articles" not in payload:
            errors = payload.get("errors") if isinstance(payload, dict) else None

            if isinstance(errors, dict):
                errors = list(errors.values())

            raise self._refused(
                "; ".join(map(str, errors))
                if isinstance(errors, list)
                else errors or "response without articles"
            )

        return [
            {
                "title": row.get("title"),
                "url": row.get("url"),
                "published_at": row.get("publishedAt"),
                "publisher": (row.get("source") or {}).get("name"),
                "summary": row.get("description"),
            }
            for row in payload["articles"]
        ]

    def _keep(self, item, ticker, company):
        # A text match is not a story about the company:
        # "Apple" is also a fruit and BAC also a blood test.
        return relevance(item, company_aliases(ticker, company)) > 0
