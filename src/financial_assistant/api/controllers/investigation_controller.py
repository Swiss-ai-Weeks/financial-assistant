from __future__ import annotations

from fastapi import APIRouter, Depends

from financial_assistant.api.dependencies import get_investigation_service
from financial_assistant.api.models import Investigation
from financial_assistant.api.schemas import StartInvestigationRequest
from financial_assistant.api.services import InvestigationService


router = APIRouter(prefix="/investigations", tags=["investigations"])


@router.get("", response_model=list[Investigation])
def list_investigations(
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.list()


@router.post("", response_model=Investigation, status_code=202)
def start_investigation(
    body: StartInvestigationRequest,
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.start(body.anomaly_id, ticker=body.ticker)


@router.get("/{investigation_id}", response_model=Investigation)
def get_investigation(
    investigation_id: str,
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.get(investigation_id)
