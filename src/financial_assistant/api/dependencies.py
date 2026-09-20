"""
Composition root.

Every repository and service is built once here and
handed to the controllers through FastAPI's Depends, so
tests can swap any of them with app.dependency_overrides.
"""

from __future__ import annotations

from functools import lru_cache

from financial_assistant.api.config import get_settings
from financial_assistant.api.repositories import (
    ArchiveNewsSource,
    CachedDocumentFetcher,
    FinnhubDownloader,
    GdeltDownloader,
    NewsArchive,
    NewsDownloader,
    InstrumentRepository,
    InvestigationRepository,
    MarketDataRepository,
    NewsRepository,
    PortfolioRepository,
    SearchProviderNewsSource,
    YahooNewsSource,
)
from financial_assistant.api.services import (
    AnomalyService,
    DiscoveryService,
    InvestigationService,
    MarketService,
    MicroscopeService,
    NewsService,
    PortfolioService,
    PostMortemService,
)
from financial_assistant.llm import OpenAICompatibleProvider
from financial_assistant.retrieval import (
    SearxngSearchProvider,
    TrafilaturaDocumentFetcher,
)
from financial_assistant.retrieval.newsapi import NewsApiSearchProvider


# -----------------------------------------------------
# Repositories
# -----------------------------------------------------


@lru_cache(maxsize=1)
def get_market_repository() -> MarketDataRepository:
    settings = get_settings()

    return MarketDataRepository(
        settings.market_cache_dir,
        history_days=settings.history_days,
        cache_minutes=settings.market_cache_minutes,
        as_of=settings.as_of,
    )


@lru_cache(maxsize=1)
def get_instrument_repository() -> InstrumentRepository:
    return InstrumentRepository(get_settings().universe_file)


@lru_cache(maxsize=1)
def get_portfolio_repository() -> PortfolioRepository:
    settings = get_settings()

    return PortfolioRepository(
        settings.state_dir / "portfolio.json",
        seed_file=settings.seed_portfolio_file,
    )


@lru_cache(maxsize=1)
def get_search_provider() -> SearxngSearchProvider | None:
    url = get_settings().searxng_url

    return SearxngSearchProvider(base_url=url) if url else None


@lru_cache(maxsize=1)
def get_news_archive() -> NewsArchive:
    return NewsArchive(get_settings().news_archive_dir)


def get_news_downloaders() -> tuple[NewsDownloader, ...]:
    """
    Providers `make news` fills the archive from. Finnhub is
    preferred when a key is configured: it is ticker-tagged
    and carries summaries. GDELT needs no key and reaches
    further back.
    """

    settings = get_settings()
    downloaders: list[NewsDownloader] = []

    if settings.finnhub_api_key:
        downloaders.append(FinnhubDownloader(settings.finnhub_api_key))

    downloaders.append(GdeltDownloader())

    return tuple(downloaders)


@lru_cache(maxsize=1)
def get_news_repository() -> NewsRepository:
    settings = get_settings()

    # The two complement each other. The archive, filled by
    # `make news`, reaches back as far as its providers do,
    # but a historical index trails the present by days.
    # Yahoo only knows the last few weeks, which are exactly
    # the ones the archive is missing. NewsService hides
    # whatever falls outside the desk's window, so both are
    # safe on a replay date.
    sources = [ArchiveNewsSource(get_news_archive()), YahooNewsSource()]

    if (search := get_search_provider()) is not None:
        sources.append(SearchProviderNewsSource(search))

    if settings.newsapi_key:
        sources.append(
            SearchProviderNewsSource(
                NewsApiSearchProvider(api_key=settings.newsapi_key)
            )
        )

    return NewsRepository(
        settings.news_cache_dir,
        tuple(sources),
        cache_minutes=settings.news_cache_minutes,
    )


@lru_cache(maxsize=1)
def get_investigation_repository() -> InvestigationRepository:
    return InvestigationRepository(get_settings().state_dir / "investigations")


# -----------------------------------------------------
# Services
# -----------------------------------------------------


@lru_cache(maxsize=1)
def get_market_service() -> MarketService:
    return MarketService(
        get_market_repository(),
        review_days=get_settings().review_days,
    )


@lru_cache(maxsize=1)
def get_anomaly_service() -> AnomalyService:
    settings = get_settings()

    return AnomalyService(
        get_portfolio_repository(),
        get_market_repository(),
        get_instrument_repository(),
        review_days=settings.review_days,
        benchmark=settings.benchmark,
        formation_observations=settings.pairs_formation_observations,
        corr_min=settings.pairs_corr_min,
        corr_min_same_sector=settings.pairs_corr_min_same_sector,
        alpha=settings.pairs_alpha,
        entry=settings.pairs_entry,
    )


@lru_cache(maxsize=1)
def get_portfolio_service() -> PortfolioService:
    settings = get_settings()

    return PortfolioService(
        get_portfolio_repository(),
        get_instrument_repository(),
        get_market_repository(),
        get_anomaly_service(),
        benchmark=settings.benchmark,
        review_days=settings.review_days,
    )


@lru_cache(maxsize=1)
def get_news_service() -> NewsService:
    settings = get_settings()

    return NewsService(
        get_news_repository(),
        get_portfolio_repository(),
        get_instrument_repository(),
        review_days=settings.review_days,
        as_of=settings.as_of,
    )


def build_llm() -> OpenAICompatibleProvider:
    settings = get_settings()

    return OpenAICompatibleProvider(
        provider_name=settings.llm_provider_name,
        model_name=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        thinking_control=settings.llm_thinking_control,
        max_tokens=settings.llm_max_tokens,
    )


@lru_cache(maxsize=1)
def get_investigation_service() -> InvestigationService:
    settings = get_settings()

    return InvestigationService(
        get_investigation_repository(),
        get_anomaly_service(),
        get_news_service(),
        llm_factory=build_llm,
        llm_base_url=settings.llm_base_url,
        llm_api_key=settings.llm_api_key,
        model=settings.llm_model,
        provider=settings.llm_provider_name,
        document_fetcher=CachedDocumentFetcher(
            TrafilaturaDocumentFetcher(),
            settings.document_cache_dir,
        ),
        search_provider=get_search_provider(),
        max_documents=settings.max_documents,
        max_claims=settings.max_claims,
        llm_workers=settings.llm_workers,
    )


@lru_cache(maxsize=1)
def get_postmortem_service() -> PostMortemService:
    settings = get_settings()

    return PostMortemService(
        get_anomaly_service(),
        get_portfolio_repository(),
        get_market_repository(),
        get_investigation_repository(),
        review_days=settings.review_days,
        benchmark=settings.benchmark,
    )


@lru_cache(maxsize=1)
def get_microscope_service() -> MicroscopeService:
    return MicroscopeService(
        get_market_repository(),
        get_portfolio_repository(),
        get_instrument_repository(),
        get_anomaly_service(),
        benchmark=get_settings().benchmark,
    )


@lru_cache(maxsize=1)
def get_discovery_service() -> DiscoveryService:
    settings = get_settings()

    return DiscoveryService(
        get_anomaly_service(),
        get_news_service(),
        get_market_repository(),
        get_portfolio_repository(),
        get_instrument_repository(),
        cache_dir=settings.analogue_cache_dir,
        formation_observations=settings.pairs_formation_observations,
        corr_min=settings.pairs_corr_min,
        corr_min_same_sector=settings.pairs_corr_min_same_sector,
        alpha=settings.pairs_alpha,
        entry=settings.pairs_entry,
        min_liquidity_musd=settings.min_liquidity_musd,
    )
