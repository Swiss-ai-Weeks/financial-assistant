from __future__ import annotations

from fastapi import APIRouter, Depends

from financial_assistant.anomaly_detection import StrategyKind
from financial_assistant.api.dependencies import (
    get_anomaly_service,
    get_portfolio_repository,
)
from financial_assistant.api.models import Anomaly
from financial_assistant.api.repositories import PortfolioRepository
from financial_assistant.api.schemas import PairScan, PairSpread, StrategyCard
from financial_assistant.api.services import AnomalyService


router = APIRouter(tags=["anomalies"])


@router.get("/anomalies", response_model=list[Anomaly])
def list_anomalies(
    ticker: str | None = None,
    strategy: StrategyKind | None = None,
    service: AnomalyService = Depends(get_anomaly_service),
):
    return service.list(ticker=ticker, strategy=strategy)


@router.get("/strategies", response_model=list[StrategyCard])
def list_strategies(
    ticker: str | None = None,
    service: AnomalyService = Depends(get_anomaly_service),
):
    return service.strategies(ticker=ticker)


@router.get("/pairs", response_model=PairScan)
def scan_pairs(
    ticker: str | None = None,
    service: AnomalyService = Depends(get_anomaly_service),
    portfolios: PortfolioRepository = Depends(get_portfolio_repository),
):
    focus = (ticker,) if ticker else portfolios.load().tickers

    return service.pair_scan(focus=focus)


@router.get("/pairs/{ticker_a}/{ticker_b}/spread", response_model=PairSpread)
def get_pair_spread(
    ticker_a: str,
    ticker_b: str,
    service: AnomalyService = Depends(get_anomaly_service),
):
    return service.pair_spread(ticker_a, ticker_b)
