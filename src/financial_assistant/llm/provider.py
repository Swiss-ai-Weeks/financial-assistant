from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


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


def complete_structured(
    provider: StructuredLLM,
    *,
    system: str,
    user: str,
    response_model: type[BaseModel],
    reasoning: bool = False,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Ask for JSON that matches `response_model`.

    "JSON mode" only promises valid JSON. On the first real
    run the model answered with field names of its own
    (`claim`, `reasoning`), a relation called "neutral", and
    dropped required fields, each time failing a whole
    investigation. With the schema handed to the decoder,
    those answers cannot be generated in the first place.

    Providers that can constrain decoding say so with
    `supports_json_schema`. Others get the plain request,
    and validation downstream is unchanged either way: the
    schema makes good answers likely, it does not replace
    checking them.

    `schema` replaces the model's own schema when a call
    knows more than the type does, such as exactly how many
    items the answer must contain.
    """

    if getattr(provider, "supports_json_schema", False):
        return provider.complete_json(
            system=system,
            user=user,
            reasoning=reasoning,
            schema=schema or response_model.model_json_schema(),
        )

    return provider.complete_json(
        system=system,
        user=user,
        reasoning=reasoning,
    )


# ModelRun fields a provider may report about its last answer.
COMPLETION_FIELDS = (
    "chosen_model_id",
    "route",
    "locality",
    "max_tokens",
    "finish_reason",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
)


def completion_metadata(provider: StructuredLLM) -> dict[str, Any]:
    """
    What the provider recorded about the answer it just gave,
    ready to be spread into a ModelRun.

    Providers that record nothing (test doubles, other
    clients) contribute nothing: execution metadata is
    reported, never estimated.
    """

    recorded = getattr(provider, "last_completion", None) or {}

    return {
        key: recorded[key]
        for key in COMPLETION_FIELDS
        if recorded.get(key) is not None
    }
