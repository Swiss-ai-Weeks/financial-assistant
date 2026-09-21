"""
Finnhub company news, live and for the news archive.

Compared with GDELT it is built for equities: articles are
tagged to a ticker by the provider rather than matched on text,
come with a summary and the publisher's own timestamp, and the
API accepts a date range. The free tier covers one year of
history at 60 requests per minute and needs an API key.
"""

from __future__ import annotations

from urllib.parse import urlencode

from .news_provider import KeyedNewsProvider


ENDPOINT = "https://finnhub.io/api/v1/company-news"
MIN_INTERVAL_SECONDS = 1.1


class FinnhubProvider(KeyedNewsProvider):
    name = "finnhub"
    key_variable = "FINNHUB_API_KEY"

    min_interval_seconds = MIN_INTERVAL_SECONDS

    # 60 requests a minute and no daily cap: the generous
    # one, so it is the provider refreshed most often.
    min_refresh_minutes = 30
    daily_budget = None

    def covers(self, ticker: str) -> bool:
        # Company news exists for US listings only. A suffixed
        # symbol (NESN.SW) is answered with an empty list or an
        # error, so it is not asked.
        return "." not in ticker

    def _request(self, ticker, company, start, end):
        params = urlencode(
            {
                "symbol": ticker,
                "from": f"{start:%Y-%m-%d}",
                "to": f"{end:%Y-%m-%d}",
                "token": self._api_key,
            }
        )

        return f"{ENDPOINT}?{params}", {}

    def _parse(self, payload):
        if isinstance(payload, dict):
            raise self._refused(
                payload.get("error") or "unexpected response",
                rate_limited="limit" in str(payload.get("error", "")).lower(),
            )

        return [
            {
                "title": row.get("headline"),
                "url": row.get("url"),
                "published_at": row.get("datetime"),
                "publisher": row.get("source"),
                "summary": row.get("summary"),
            }
            for row in payload
        ]


# The name it had when it only filled the archive.
FinnhubDownloader = FinnhubProvider
