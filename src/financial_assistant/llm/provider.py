from __future__ import annotations

from typing import Any, Protocol


class StructuredLLM(Protocol):
    provider_name: str
    model_name: str

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        reasoning: bool = False,
    ) -> dict[str, Any]:
        ...
