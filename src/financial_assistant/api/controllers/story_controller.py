"""
The three stories are one loop over the same engine:

    post-mortem   past      what did I miss?
    microscope    present   what am I looking at?
    discovery     future    what should I be looking at?
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from financial_assistant.api.dependencies import (
    get_discovery_service,
    get_microscope_service,
    get_postmortem_service,
)
from financial_assistant.api.schemas import (
    DiscoveryJob,
    Microscope,
    PostMortem,
    StartDiscoveryRequest,
)
from financial_assistant.api.services import (
    DiscoveryService,
    MicroscopeService,
    PostMortemService,
)


router = APIRouter(tags=["stories"])


@router.get("/postmortem", response_model=PostMortem)
def get_postmortem(
    service: PostMortemService = Depends(get_postmortem_service),
):
    return service.review()


@router.get("/microscope/{ticker}", response_model=Microscope)
def get_microscope(
    ticker: str,
    horizon: str = Query(default="1w"),
    service: MicroscopeService = Depends(get_microscope_service),
):
    return service.read(ticker, horizon)


@router.post("/discovery", response_model=DiscoveryJob, status_code=202)
def start_discovery(
    body: StartDiscoveryRequest | None = None,
    service: DiscoveryService = Depends(get_discovery_service),
):
    return service.start(body.model_id if body else None)


@router.get("/discovery", response_model=DiscoveryJob)
def get_discovery(
    service: DiscoveryService = Depends(get_discovery_service),
):
    return service.job()
