from __future__ import annotations

from fastapi import APIRouter, Depends

from financial_assistant.api.config import Settings, get_settings
from financial_assistant.api.clock import DeskClock
from financial_assistant.api.dependencies import (
    get_anomaly_service,
    get_clock,
    get_discovery_service,
    get_investigation_service,
    get_news_service,
)
from financial_assistant.api.errors import DeskError
from financial_assistant.api.schemas import (
    ServiceStatus,
    SystemStatus,
    TimeTravelRequest,
)
from financial_assistant.api.services import (
    AnomalyService,
    DiscoveryService,
)
from financial_assistant.api.services import InvestigationService, NewsService


router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/system", response_model=SystemStatus)
def get_system_status(
    settings: Settings = Depends(get_settings),
    investigations: InvestigationService = Depends(get_investigation_service),
    news: NewsService = Depends(get_news_service),
    clock: DeskClock = Depends(get_clock),
):
    return SystemStatus(
        as_of=clock.as_of,
        llm=investigations.llm_status(),
        llm_local=settings.llm_is_local,
        model=settings.llm_model,
        provider=settings.llm_provider_name,
        news_sources=list(news.source_names),
        search=ServiceStatus(
            name="searxng",
            online=settings.searxng_url is not None,
            detail=settings.searxng_url or "SEARXNG_URL not set",
        ),
    )


@router.put("/system/as-of", response_model=SystemStatus)
def travel_in_time(
    body: TimeTravelRequest,
    settings: Settings = Depends(get_settings),
    investigations: InvestigationService = Depends(get_investigation_service),
    news: NewsService = Depends(get_news_service),
    anomalies: AnomalyService = Depends(get_anomaly_service),
    discovery: DiscoveryService = Depends(get_discovery_service),
    clock: DeskClock = Depends(get_clock),
):
    """
    Move the whole desk to a past session, or back to today.

    Prices and news after that date stop existing for every
    service, so anomalies, findings and evidence are what they
    would have been then. Investigations already saved keep
    their own cutoff and are untouched.
    """

    try:
        clock.set(body.as_of)
    except ValueError as error:
        raise DeskError(str(error)) from error

    # Everything memoised was computed from another market.
    anomalies.invalidate()
    discovery.reset()

    return get_system_status(settings, investigations, news, clock)
