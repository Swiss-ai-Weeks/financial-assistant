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
from financial_assistant.api.schemas import AnomalyNews, KeyDate
from financial_assistant.api.services.anomaly_service import session_close


LOOKBACK_DAYS = 7
HINDSIGHT_DAYS = 3

# News counts as "around" a key date from this many days
# before it until the close of that session. The cause of a
# move is published before or on the day, never after.
KEY_DATE_DAYS_BEFORE = 2

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

        key_dates = self.key_dates(anomaly)

        admissible = self._by_key_date(
            [item for item in unique.values() if item.published_at <= cutoff],
            scores,
            key_dates,
        )

        hindsight = sorted(
            (item for item in unique.values() if item.published_at > cutoff),
            key=lambda item: item.published_at,
        )

        return AnomalyNews(
            anomaly_id=anomaly.anomaly_id,
            cutoff=cutoff.isoformat(),
            key_dates=key_dates,
            admissible=admissible,
            hindsight=hindsight,
        )

    @staticmethod
    def key_dates(anomaly: Anomaly) -> list[KeyDate]:
        """
        A relationship does not break on the day it is looked
        at. It has an onset (first session beyond the
        threshold), a peak (most stretched) and a latest
        state, and what caused it is dated near the first two.
        A single-session signal has only its own date.
        """

        def parsed(name: str):
            value = anomaly.metrics.get(name)

            return datetime.fromisoformat(str(value)).date() if value else None

        candidates = (
            ("onset", parsed("first_flag")),
            ("peak", parsed("peak_date")),
            ("latest", anomaly.observed_on),
        )

        dates: list[KeyDate] = []

        for label, day in candidates:
            if day is None:
                continue

            same = next((k for k in dates if k.day == day), None)

            if same is None:
                dates.append(KeyDate(label=label, day=day))
            else:
                same.label += f" / {label}"

        return dates

    @staticmethod
    def _by_key_date(
        items: list[NewsItem],
        scores: dict[str, int],
        key_dates: list[KeyDate],
    ) -> list[NewsItem]:
        """
        Order evidence so that whatever reads the first few
        articles, a person, triage or an investigation, reads
        around every key date, not only the most recent one.

        Ordered by recency alone, a month-long divergence was
        explained from the news of the day it was detected:
        twelve of twelve articles from the last session and
        none from the week it began.

        Articles around each key date are ranked by whether
        they name the company, then by closeness to the date,
        and the dates take turns. Everything else follows,
        most relevant and most recent first.
        """

        def ranked(bucket: list[NewsItem], close_of_day: datetime):
            return sorted(
                bucket,
                key=lambda item: (
                    -scores[item.news_id],
                    close_of_day - item.published_at,
                ),
            )

        buckets = []
        taken: set[str] = set()

        for key in key_dates:
            close_of_day = session_close(key.day)
            opens = close_of_day - timedelta(days=KEY_DATE_DAYS_BEFORE + 1)

            bucket = [
                item
                for item in items
                if opens < item.published_at <= close_of_day
                and item.news_id not in taken
            ]

            taken.update(item.news_id for item in bucket)
            buckets.append(ranked(bucket, close_of_day))

        ordered: list[NewsItem] = []

        while any(buckets):
            for bucket in buckets:
                if bucket:
                    ordered.append(bucket.pop(0))

        rest = sorted(
            (item for item in items if item.news_id not in taken),
            key=lambda item: (scores[item.news_id], item.published_at),
            reverse=True,
        )

        return ordered + rest

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
