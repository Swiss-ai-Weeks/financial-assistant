from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from financial_assistant.api.dependencies import (
    get_anomaly_service,
    get_news_service,
)
from financial_assistant.api.models import NewsItem
from financial_assistant.api.schemas import AnomalyNews, NewsSourceStatus
from financial_assistant.api.services import AnomalyService, NewsService


router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=list[NewsItem])
def get_portfolio_news(
    limit: int = Query(default=80, ge=1, le=300),
    service: NewsService = Depends(get_news_service),
):
    return service.portfolio_feed(limit=limit)


# Declared before /{ticker}, which would otherwise read
# "sources" as a ticker.
@router.get("/sources", response_model=list[NewsSourceStatus])
def get_news_sources(service: NewsService = Depends(get_news_service)):
    return service.sources()


@router.get("/anomaly/{anomaly_id}", response_model=AnomalyNews)
def get_anomaly_news(
    anomaly_id: str,
    ticker: str | None = None,
    service: NewsService = Depends(get_news_service),
    anomalies: AnomalyService = Depends(get_anomaly_service),
):
    anomaly, _ = anomalies.find(anomaly_id, ticker=ticker)

    return service.around(anomaly)


@router.get("/{ticker}", response_model=list[NewsItem])
def get_ticker_news(
    ticker: str,
    limit: int = Query(default=60, ge=1, le=300),
    service: NewsService = Depends(get_news_service),
):
    return service.feed(ticker, limit=limit)


@router.post("/{ticker}/refresh", response_model=list[NewsItem])
def refresh_ticker_news(
    ticker: str,
    limit: int = Query(default=60, ge=1, le=300),
    service: NewsService = Depends(get_news_service),
):
    return service.refresh(ticker, limit=limit)
