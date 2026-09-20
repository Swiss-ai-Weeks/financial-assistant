"""
Finnhub company news as a provider for the news archive.

Compared with GDELT it is built for equities: articles are
tagged to a ticker by the provider rather than matched on text,
come with a summary and the publisher's own timestamp, and the
API accepts a date range. The free tier covers one year of
history at 60 requests per minute and needs an API key.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha1
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from financial_assistant.api.models import NewsItem


ENDPOINT = "https://finnhub.io/api/v1/company-news"
MIN_INTERVAL_SECONDS = 1.1


def _http_get(url: str) -> str:
    request = Request(url, headers={"User-Agent": "ClaimGraph/0.3"})

    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


class FinnhubDownloader:
    name = "finnhub"

    def __init__(
        self,
        api_key: str,
        *,
        http_get: Callable[[str], str] = _http_get,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is not configured")

        self._api_key = api_key
        self._http_get = http_get
        self._sleep = sleep
        self._clock = clock

        self._lock = threading.Lock()
        self._last_request: float | None = None

    def signature(self, ticker: str, company: str) -> str:
        # Queried by symbol only, so there is nothing to vary.
        return "v1"

    def fetch(self, ticker, company, *, start, end) -> list[NewsItem]:
        params = urlencode(
            {
                "symbol": ticker,
                "from": f"{start:%Y-%m-%d}",
                "to": f"{end:%Y-%m-%d}",
                "token": self._api_key,
            }
        )

        with self._lock:
            if self._last_request is not None:
                remaining = MIN_INTERVAL_SECONDS - (
                    self._clock() - self._last_request
                )

                if remaining > 0:
                    self._sleep(remaining)

            self._last_request = self._clock()
            rows = json.loads(self._http_get(f"{ENDPOINT}?{params}"))

        return [
            NewsItem(
                news_id="NEWS-" + sha1(row["url"].encode()).hexdigest()[:12],
                ticker=ticker,
                title=" ".join(row["headline"].split()),
                url=row["url"],
                publisher=row.get("source"),
                published_at=datetime.fromtimestamp(
                    row["datetime"], tz=timezone.utc
                ),
                summary=(row.get("summary") or "").strip(),
                provider=self.name,
            )
            for row in rows
            if row.get("url") and row.get("headline") and row.get("datetime")
        ]
