from __future__ import annotations

from fastapi import APIRouter, Depends

from financial_assistant.api.config import Settings, get_settings
from financial_assistant.api.dependencies import (
    get_investigation_service,
    get_news_service,
)
from financial_assistant.api.schemas import ServiceStatus, SystemStatus
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
):
    return SystemStatus(
        as_of=settings.as_of,
        llm=investigations.llm_status(),
        model=settings.llm_model,
        provider=settings.llm_provider_name,
        news_sources=list(news.source_names),
        search=ServiceStatus(
            name="searxng",
            online=settings.searxng_url is not None,
            detail=settings.searxng_url or "SEARXNG_URL not set",
        ),
    )
