from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from financial_assistant.api.models import Anomaly, NewsItem
from financial_assistant.api.repositories import (
    NewsRepository,
    PortfolioRepository,
)
from financial_assistant.api.schemas import AnomalyNews
from financial_assistant.api.services.anomaly_service import session_close


LOOKBACK_DAYS = 7
HINDSIGHT_DAYS = 3


class NewsService:
    """
    News is the explanatory layer of the desk: every
    anomaly is read against what was public when it
    happened.
    """

    def __init__(self, news: NewsRepository, portfolios: PortfolioRepository):
        self._news = news
        self._portfolios = portfolios

    @property
    def source_names(self) -> tuple[str, ...]:
        return self._news.source_names

    def feed(self, ticker: str, *, limit: int = 60) -> list[NewsItem]:
        symbol = ticker.strip().upper()

        return list(self._news.get(symbol, self._company(symbol)))[:limit]

    def portfolio_feed(self, *, limit: int = 80) -> list[NewsItem]:
        tickers = self._portfolios.load().tickers

        if not tickers:
            return []

        with ThreadPoolExecutor(max_workers=min(8, len(tickers))) as pool:
            feeds = pool.map(lambda t: self.feed(t, limit=limit), tickers)

        # The same story is often tagged to several
        # holdings. Keep it once.
        unique: dict[str, NewsItem] = {}

        for feed in feeds:
            for item in feed:
                unique.setdefault(item.news_id, item)

        return sorted(
            unique.values(),
            key=lambda item: item.published_at,
            reverse=True,
        )[:limit]

    def around(self, anomaly: Anomaly) -> AnomalyNews:
        """
        News for every leg of the anomaly, split at the
        evidence cutoff.
        """

        cutoff = session_close(anomaly.observed_on)
        opened = self.evidence_window_start(anomaly)
        closed = cutoff + timedelta(days=HINDSIGHT_DAYS)

        unique: dict[str, NewsItem] = {}

        for ticker in (anomaly.ticker, *anomaly.related_tickers):
            for item in self._news.get(ticker, self._company(ticker)):
                if opened <= item.published_at <= closed:
                    unique.setdefault(item.news_id, item)

        ordered = sorted(
            unique.values(),
            key=lambda item: item.published_at,
            reverse=True,
        )

        return AnomalyNews(
            anomaly_id=anomaly.anomaly_id,
            cutoff=cutoff.isoformat(),
            admissible=[i for i in ordered if i.published_at <= cutoff],
            hindsight=[i for i in ordered if i.published_at > cutoff],
        )

    @staticmethod
    def evidence_window_start(anomaly: Anomaly) -> datetime:
        """
        A pair divergence builds over days, so its window
        opens before the first flagged session rather
        than before the latest one.
        """

        first_flag = anomaly.metrics.get("first_flag")

        anchor = (
            datetime.fromisoformat(str(first_flag)).date()
            if first_flag
            else anomaly.observed_on
        )

        return session_close(anchor) - timedelta(days=LOOKBACK_DAYS)

    def _company(self, ticker: str) -> str:
        for position in self._portfolios.load().positions:
            if position.ticker == ticker:
                return position.name

        return ticker
