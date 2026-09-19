from __future__ import annotations

from fastapi import APIRouter, Depends

from financial_assistant.api.dependencies import get_portfolio_service
from financial_assistant.api.schemas import (
    AddPositionRequest,
    AddPositionResponse,
    PortfolioView,
)
from financial_assistant.api.services import PortfolioService


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioView)
def get_portfolio(
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.view()


@router.post("/positions", response_model=AddPositionResponse, status_code=201)
def add_position(
    body: AddPositionRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.add_position(body.ticker, body.shares)


@router.delete("/positions/{ticker}", response_model=PortfolioView)
def remove_position(
    ticker: str,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.remove_position(ticker)


@router.post("/reset", response_model=PortfolioView)
def reset_portfolio(
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.reset()
