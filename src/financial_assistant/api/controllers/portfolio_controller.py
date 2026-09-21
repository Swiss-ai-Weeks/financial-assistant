from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from financial_assistant.api.dependencies import get_portfolio_service
from financial_assistant.api.schemas import (
    AddPositionRequest,
    AddPositionResponse,
    MarketContextRequest,
    PortfolioView,
    SetWeightsRequest,
    SimulateOverlayRequest,
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


@router.put("/weights", response_model=PortfolioView)
def set_weights(
    body: SetWeightsRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.set_weights(
        [(position.ticker, position.weight) for position in body.positions],
        notional=body.notional,
        name=body.name,
    )


# The three below return the calculation records of
# financial_assistant.portfolio as they are: every figure
# carries its formula, its version and its inputs.


@router.get("/analysis", response_model=dict[str, Any])
def analyse_portfolio(
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.analysis()


@router.post("/simulate", response_model=dict[str, Any])
def simulate_overlay(
    body: SimulateOverlayRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.simulate(
        body.ticker_a,
        body.ticker_b,
        gross_overlay=body.gross_overlay,
        lookback=body.lookback,
    )


@router.post("/market", response_model=dict[str, Any])
def market_context(
    body: MarketContextRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.market(body.tickers)
