"""
Composition root.

Every repository and service is built once here and
handed to the controllers through FastAPI's Depends, so
tests can swap any of them with app.dependency_overrides.
"""

from __future__ import annotations

from functools import lru_cache

from financial_assistant.api.clock import DeskClock
from financial_assistant.api.config import get_settings
from financial_assistant.api.repositories import (
    AlphaVantageProvider,
    ArchiveNewsSource,
    CachedDocumentFetcher,
    EodhdProvider,
    FinnhubProvider,
    GdeltDownloader,
    GNewsProvider,
    KeyedNewsProvider,
    MarketauxProvider,
    NewsApiProvider,
    NewsArchive,
    NewsDownloader,
    InstrumentRepository,
    InvestigationRepository,
    MarketDataRepository,
    NewsRepository,
    PortfolioRepository,
    SearchProviderNewsSource,
    TriageRepository,
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
from financial_assistant.copilot import CopilotService
from financial_assistant.fundamentals.service import (
    FundamentalsService,
    load_pair,
)
from financial_assistant.llm import OpenAICompatibleProvider
from financial_assistant.llm.model_registry import (
    ModelRegistry,
    ModelSpec,
    build_registry,
)
from financial_assistant.retrieval import (
    SearxngSearchProvider,
    TrafilaturaDocumentFetcher,
)


# -----------------------------------------------------
# Repositories
# -----------------------------------------------------


@lru_cache(maxsize=1)
def get_clock() -> DeskClock:
    """Starts on AS_OF from .env; the desk may move it while running."""

    return DeskClock(get_settings().as_of)


@lru_cache(maxsize=1)
def get_market_repository() -> MarketDataRepository:
    settings = get_settings()

    return MarketDataRepository(
        settings.market_cache_dir,
        history_days=settings.history_days,
        cache_minutes=settings.market_cache_minutes,
        as_of=get_clock(),
    )


@lru_cache(maxsize=1)
def get_instrument_repository() -> InstrumentRepository:
    settings = get_settings()

    # Which sectors come first when the universe is capped: the
    # book's own. Read once: a very different book needs a
    # restart to re-prioritise, which is a fair price for a
    # universe that does not change under a running scan.
    catalogue = InstrumentRepository(
        settings.universe_file,
        catalog_file=settings.universe_catalog,
    )

    book = get_portfolio_repository().load().tickers

    return InstrumentRepository(
        settings.universe_file,
        catalog_file=settings.universe_catalog,
        max_size=settings.universe_max,
        priority_sectors=tuple(
            sector
            for ticker in book
            if (sector := catalogue.sectors.get(ticker)) is not None
        ),
    )


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


# Every provider that needs a key, in the order they are
# asked. The order matters: the first provider to report a
# story keeps it, so the ones that tag by ticker and carry a
# summary come before the ones that match text, and Alpha
# Vantage, with a quota of 25 requests a day, comes last.
KEYED_NEWS_PROVIDERS = (
    (FinnhubProvider, "finnhub_api_key"),
    (EodhdProvider, "eodhd_api_key"),
    (MarketauxProvider, "marketaux_api_key"),
    (GNewsProvider, "gnews_api_key"),
    (NewsApiProvider, "newsapi_key"),
    (AlphaVantageProvider, "alphavantage_api_key"),
)


@lru_cache(maxsize=1)
def get_news_providers() -> tuple[KeyedNewsProvider, ...]:
    """
    One instance per provider with a key, shared by the desk
    and by `make news`, so a provider's throttle holds
    whoever is asking.
    """

    settings = get_settings()

    return tuple(
        provider(getattr(settings, field))
        for provider, field in KEYED_NEWS_PROVIDERS
        if getattr(settings, field)
    )


def get_news_downloaders() -> tuple[NewsDownloader, ...]:
    """
    Providers `make news` fills the archive from: every
    keyed provider that is configured, all of which accept a
    date range, then GDELT, which needs no key and reaches
    further back but is slow and matches text.
    """

    return (*get_news_providers(), GdeltDownloader())


@lru_cache(maxsize=1)
def get_news_repository() -> NewsRepository:
    settings = get_settings()

    # They complement each other. The archive, filled by
    # `make news`, reaches back as far as its providers do,
    # but a historical index trails the present by days.
    # Yahoo only knows the last few weeks, which are exactly
    # the ones the archive is missing, and the keyed
    # providers add what Yahoo does not carry. NewsService
    # hides whatever falls outside the desk's window, so all
    # are safe on a replay date.
    sources = [
        ArchiveNewsSource(get_news_archive()),
        YahooNewsSource(),
        *get_news_providers(),
        # Keyless and slow (see its docstring): last, so it
        # adds what the others missed rather than carrying
        # the feed.
        GdeltDownloader(),
    ]

    if (search := get_search_provider()) is not None:
        sources.append(SearchProviderNewsSource(search))

    return NewsRepository(
        settings.news_cache_dir,
        tuple(sources),
        cache_minutes=settings.news_cache_minutes,
        unconfigured=tuple(
            provider.name
            for provider, field in KEYED_NEWS_PROVIDERS
            if not getattr(settings, field)
        ),
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
        recalibrate_every=settings.pairs_recalibrate_sessions or None,
        recalibration_window=settings.pairs_recalibration_window or None,
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
        as_of=get_clock(),
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
        timeout_seconds=settings.llm_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    """
    The LLM_PROFILE model stays the default; Apertus and
    anything in PYTHIA_MODELS are offered next to it.
    """

    settings = get_settings()

    return build_registry(
        ModelSpec(
            id=settings.llm_model_id,
            label=(
                "Nemotron 3.5 Lightning"
                if settings.llm_model_id == "nemotron"
                else ""
            ),
            origin="NVIDIA" if settings.llm_model_id == "nemotron" else "",
            provider=settings.llm_provider_name,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key_env="LLM_API_KEY",
            thinking_control=settings.llm_thinking_control,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
            workers=settings.llm_workers,
        )
    )


@lru_cache(maxsize=1)
def get_copilot_service() -> CopilotService:
    return CopilotService(get_model_registry())


def get_fundamentals_loader():
    """
    SEC Company Facts for the legs of an anomaly, selected as
    of its evidence cutoff. None when SEC_USER_AGENT is unset.
    """

    settings = get_settings()

    if not settings.sec_user_agent:
        return None

    from financial_assistant.fundamentals.sec import SECProvider

    def load(tickers, as_of):
        service = FundamentalsService(
            SECProvider(
                cache_dir=settings.fundamentals_cache_dir,
                user_agent=settings.sec_user_agent,
            )
        )

        return load_pair(tickers, as_of, service=service)

    return load


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
        llm_is_local=settings.llm_is_local,
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
        registry=get_model_registry(),
        fundamentals_loader=get_fundamentals_loader(),
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
        triage_store=TriageRepository(settings.state_dir / "triage"),
        llm_factory=build_llm,
        llm_available=lambda: get_investigation_service().llm_status().online,
        llm_workers=settings.llm_workers,
        registry=get_model_registry(),
    )
