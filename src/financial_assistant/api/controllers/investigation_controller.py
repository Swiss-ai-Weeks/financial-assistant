from __future__ import annotations

from fastapi import APIRouter, Depends

from financial_assistant.api.dependencies import get_investigation_service
from financial_assistant.api.models import Investigation
from financial_assistant.api.schemas import (
    ModelList,
    StartFollowUpRequest,
    StartInvestigationRequest,
)
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
    return service.start(
        body.anomaly_id,
        ticker=body.ticker,
        model_id=body.model_id,
    )


# Declared before /{investigation_id}, which would otherwise
# read "models" as an id.
@router.get("/models", response_model=ModelList)
def list_models(
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.models()


@router.get("/{investigation_id}", response_model=Investigation)
def get_investigation(
    investigation_id: str,
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.get(investigation_id)


@router.post(
    "/{investigation_id}/followups",
    response_model=Investigation,
    status_code=202,
)
def start_follow_up(
    investigation_id: str,
    body: StartFollowUpRequest,
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.follow_up(
        investigation_id,
        body.requirement_id,
        model_id=body.model_id,
    )
