from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from financial_assistant.api.models import Anomaly, NewsItem
from financial_assistant.api.relevance import (
    company_aliases,
    one_per_story,
    relevance,
)
from financial_assistant.api.repositories import (
    InstrumentRepository,
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

    def __init__(
        self,
        news: NewsRepository,
        portfolios: PortfolioRepository,
        instruments: InstrumentRepository,
        *,
        review_days: int,
        as_of: date | None = None,
    ):
        self._news = news
        self._portfolios = portfolios
        self._instruments = instruments
        self._review_days = review_days
        self._as_of = as_of

    @property
    def source_names(self) -> tuple[str, ...]:
        return self._news.source_names

    def window(self) -> tuple[datetime, datetime]:
        """
        The period the desk reads news for: the review
        window, the lookback before its first session, and
        a few days of hindsight after its last.

        On a replay date this is what hides news from the
        "future", exactly as the market data repository
        hides later prices.
        """

        last_close = (
            session_close(self._as_of)
            if self._as_of
            else datetime.now(timezone.utc)
        )

        return (
            last_close - timedelta(days=self._review_days + LOOKBACK_DAYS),
            last_close + timedelta(days=HINDSIGHT_DAYS),
        )

    def feed(self, ticker: str, *, limit: int = 60) -> list[NewsItem]:
        return self._wire(ticker.strip().upper())[:limit]

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
        scores: dict[str, int] = {}

        for ticker in (anomaly.ticker, *anomaly.related_tickers):
            company = self._company(ticker)
            aliases = company_aliases(ticker, company)

            for item in self._wire(ticker):
                if not opened <= item.published_at <= closed:
                    continue

                unique.setdefault(item.news_id, item)

                scores[item.news_id] = max(
                    scores.get(item.news_id, 0),
                    relevance(item, aliases),
                )

        # Feeds tag a story to every ticker it mentions in
        # passing. Stories that name the company come first,
        # then the freshest.
        ordered = sorted(
            unique.values(),
            key=lambda item: (scores[item.news_id], item.published_at),
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

    def _wire(self, ticker: str) -> list[NewsItem]:
        start, end = self.window()

        return one_per_story(
            item
            for item in self._news.get(
                ticker, self._company(ticker), start=start, end=end
            )
            if start <= item.published_at <= end
        )

    def _company(self, ticker: str) -> str:
        for position in self._portfolios.load().positions:
            if position.ticker == ticker and position.name:
                return position.name

        # The other leg of a pair is usually not held.
        return self._instruments.describe(ticker).name
