"""
Marketaux, live and for the news archive.

Entity-tagged: `filter_entities` keeps only stories in which
the symbol was recognised, so nothing has to be matched on
text. Accepts a time range to the minute. The free tier is
100 requests a day and only a few articles per request, so it
adds depth to a feed rather than carrying one.
"""

from __future__ import annotations

from urllib.parse import urlencode

from .news_provider import KeyedNewsProvider


ENDPOINT = "https://api.marketaux.com/v1/news/all"

# The plan decides how many actually come back.
MAX_ARTICLES = 50


class MarketauxProvider(KeyedNewsProvider):
    name = "marketaux"
    key_variable = "MARKETAUX_API_KEY"

    min_interval_seconds = 1.0

    min_refresh_minutes = 4 * 60
    daily_budget = 100

    def _request(self, ticker, company, start, end):
        params = urlencode(
            {
                "symbols": ticker,
                "filter_entities": "true",
                "language": "en",
                "published_after": f"{start:%Y-%m-%dT%H:%M}",
                "published_before": f"{end:%Y-%m-%dT%H:%M}",
                "limit": MAX_ARTICLES,
                "api_token": self._api_key,
            }
        )

        return f"{ENDPOINT}?{params}", {}

    def _parse(self, payload):
        if not isinstance(payload, dict) or "data" not in payload:
            error = payload.get("error") if isinstance(payload, dict) else None
            error = error if isinstance(error, dict) else {}

            raise self._refused(
                error.get("message") or "response without data",
                rate_limited="limit" in str(error.get("code", "")),
            )

        return [
            {
                "title": row.get("title"),
                "url": row.get("url"),
                "published_at": row.get("published_at"),
                "publisher": row.get("source"),
                "summary": row.get("description") or row.get("snippet"),
            }
            for row in payload["data"]
        ]
