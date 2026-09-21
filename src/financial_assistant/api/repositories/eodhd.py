"""
EODHD financial news, live and for the news archive.

The one keyed provider that follows a company outside the US:
it is queried by exchange-qualified symbol (SAP.XETRA), returns
the article body rather than a summary, and accepts a date
range. It is also the most expensive: one news request is
billed as ten API calls and the free tier has twenty a day.
"""

from __future__ import annotations

from urllib.parse import urlencode

from .news_provider import KeyedNewsProvider


ENDPOINT = "https://eodhd.com/api/news"
MAX_ARTICLES = 100
SUMMARY_CHARS = 400

# Yahoo suffix -> EODHD exchange code, for the suffixes the
# desk's universes use. Most are the same two letters; the
# ones that differ are the reason this table exists.
EXCHANGES = {
    "DE": "XETRA",
    "L": "LSE",
    "PA": "PA",
    "SW": "SW",
    "MI": "MI",
    "AS": "AS",
    "ST": "ST",
    "CO": "CO",
    "HE": "HE",
    "OL": "OL",
    "MC": "MC",
    "BR": "BR",
    "LS": "LS",
    "VI": "VI",
    "IR": "IR",
}


def eodhd_symbol(ticker: str) -> str:
    """
    AAPL -> AAPL.US, SAP.DE -> SAP.XETRA. A suffix that is
    not in the table is passed through: EODHD either knows
    it under the same code or returns nothing.
    """

    root, dot, suffix = ticker.strip().upper().rpartition(".")

    if not dot:
        return f"{suffix}.US"

    return f"{root}.{EXCHANGES.get(suffix, suffix)}"


class EodhdProvider(KeyedNewsProvider):
    name = "eodhd"
    key_variable = "EODHD_API_KEY"

    min_interval_seconds = 1.0

    # Twenty API calls a day on the free tier and a news
    # request costs ten (five, plus five per ticker), which
    # leaves two requests. A paid key should raise both.
    min_refresh_minutes = 24 * 60
    daily_budget = 2

    def _request(self, ticker, company, start, end):
        params = urlencode(
            {
                "s": eodhd_symbol(ticker),
                "from": f"{start:%Y-%m-%d}",
                "to": f"{end:%Y-%m-%d}",
                "limit": MAX_ARTICLES,
                "offset": 0,
                "api_token": self._api_key,
                "fmt": "json",
            }
        )

        return f"{ENDPOINT}?{params}", {}

    def _parse(self, payload):
        if not isinstance(payload, list):
            message = (
                payload.get("message") or payload.get("error")
                if isinstance(payload, dict)
                else None
            )

            raise self._refused(message or "unexpected response")

        return [
            {
                "title": row.get("title"),
                "url": row.get("link"),
                "published_at": row.get("date"),
                # The publisher is not a field of its own.
                "publisher": None,
                # The body is not ours to store. Its opening
                # is what a summary would have said.
                "summary": " ".join(
                    str(row.get("content") or "").split()
                )[:SUMMARY_CHARS],
            }
            for row in payload
            if isinstance(row, dict)
        ]
