from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from financial_assistant.api.dependencies import get_portfolio_repository, get_wire_service
from financial_assistant.api.services.wire_service import WireService

router = APIRouter(prefix="/wire", tags=["wire"])


@router.get("/status")
def wire_status(service: WireService = Depends(get_wire_service)):
    return service.status()


@router.get("/feed")
def wire_feed(
    days: int = Query(default=30, ge=1, le=400),
    ticker: str | None = Query(default=None),
    service: WireService = Depends(get_wire_service),
    portfolios=Depends(get_portfolio_repository),
):
    tickers = [ticker] if ticker else list(portfolios.load().tickers)

    return service.feed(tickers, days=days)


@router.get("/graph/{ticker}")
def wire_graph(
    ticker: str,
    days: int = Query(default=30, ge=1, le=400),
    service: WireService = Depends(get_wire_service),
):
    return service.graph(ticker, days=days)


@router.get("/signals/{ticker}")
def wire_signals(ticker: str, service: WireService = Depends(get_wire_service)):
    return service.signals(ticker)
