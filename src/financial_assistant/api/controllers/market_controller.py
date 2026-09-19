from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from financial_assistant.api.dependencies import (
    get_instrument_repository,
    get_market_service,
    get_portfolio_repository,
)
from financial_assistant.api.models import Instrument
from financial_assistant.api.repositories import (
    InstrumentRepository,
    PortfolioRepository,
)
from financial_assistant.api.schemas import CandleSeries, Quote
from financial_assistant.api.services import MarketService


router = APIRouter(tags=["market"])


@router.get("/instruments/search", response_model=list[Instrument])
def search_instruments(
    q: str = Query(min_length=1, max_length=40),
    instruments: InstrumentRepository = Depends(get_instrument_repository),
):
    return instruments.search(q)


@router.get("/market/tape", response_model=list[Quote])
def get_tape(
    service: MarketService = Depends(get_market_service),
    portfolios: PortfolioRepository = Depends(get_portfolio_repository),
):
    return service.quotes(portfolios.load().tickers)


@router.get("/market/{ticker}/quote", response_model=Quote)
def get_quote(
    ticker: str,
    service: MarketService = Depends(get_market_service),
):
    return service.quote(ticker)


@router.get("/market/{ticker}/candles", response_model=CandleSeries)
def get_candles(
    ticker: str,
    days: int = Query(default=180, ge=20, le=800),
    service: MarketService = Depends(get_market_service),
):
    return service.candles(ticker, days=days)
