"""
Alpha Vantage NEWS_SENTIMENT, live and for the news archive.

Ticker-tagged like Finnhub, with a summary and a timestamp to
the second, and it accepts a time range. What it lacks is
quota: the free tier allows about 25 requests a DAY, so it is
refreshed rarely and listed last among the downloaders.
"""

from __future__ import annotations

from urllib.parse import urlencode

from .news_provider import KeyedNewsProvider


ENDPOINT = "https://www.alphavantage.co/query"
MAX_ARTICLES = 200

# Refusals arrive as HTTP 200 with one of these keys and
# no `feed`: "Note" and "Information" for a spent quota or
# a premium endpoint, "Error Message" for a bad call.
REFUSAL_KEYS = ("Note", "Information", "Error Message")


class AlphaVantageProvider(KeyedNewsProvider):
    name = "alphavantage"
    key_variable = "ALPHAVANTAGE_API_KEY"

    min_interval_seconds = 1.2

    # 25 a day: a ten-name book refreshed twice.
    min_refresh_minutes = 12 * 60
    daily_budget = 25

    def covers(self, ticker: str) -> bool:
        # Tickers are US symbols. An unknown one is answered
        # with "Invalid inputs", which still costs a request.
        return "." not in ticker

    def _request(self, ticker, company, start, end):
        params = urlencode(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "time_from": f"{start:%Y%m%dT%H%M}",
                "time_to": f"{end:%Y%m%dT%H%M}",
                "limit": MAX_ARTICLES,
                "sort": "LATEST",
                "apikey": self._api_key,
            }
        )

        return f"{ENDPOINT}?{params}", {}

    def _parse(self, payload):
        if not isinstance(payload, dict):
            raise self._refused("unexpected response")

        if "feed" not in payload:
            for key in REFUSAL_KEYS:
                if key in payload:
                    raise self._refused(
                        payload[key],
                        rate_limited=key != "Error Message",
                    )

            raise self._refused("response without a feed")

        return [
            {
                "title": row.get("title"),
                "url": row.get("url"),
                # 20240102T153000, in UTC.
                "published_at": row.get("time_published"),
                "publisher": row.get("source"),
                "summary": row.get("summary"),
            }
            for row in payload["feed"]
        ]
