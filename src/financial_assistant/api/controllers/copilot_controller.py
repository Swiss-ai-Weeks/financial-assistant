from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError

from financial_assistant.api.dependencies import get_copilot_service
from financial_assistant.api.errors import DeskError, UpstreamUnavailable
from financial_assistant.copilot import CopilotService
from financial_assistant.llm import LLMTransportError
from financial_assistant.llm.model_registry import RoutingError


router = APIRouter(prefix="/copilot", tags=["copilot"])

# The view context is capped at 24 KB by its own validator;
# this bounds the whole body before it is even parsed.
MAX_BODY_CHARS = 40000


@router.post("")
def ask_copilot(
    body: dict[str, Any] = Body(...),
    service: CopilotService = Depends(get_copilot_service),
):
    """
    Commentary on the ClaimGraph view the browser describes,
    plus at most one validated UI action. Never a graph edit.
    """

    try:
        return service.ask(body)

    except RoutingError as error:
        raise DeskError(f"{error.code}: {error}") from error

    except LLMTransportError as error:
        raise UpstreamUnavailable(str(error)) from error

    except (ValidationError, ValueError) as error:
        # The model answered outside the contract, or the view
        # context was malformed. Neither is retried silently.
        raise DeskError(str(error).splitlines()[0]) from error
