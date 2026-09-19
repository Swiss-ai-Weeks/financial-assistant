from __future__ import annotations

import json

from typing import Any

from urllib.request import (
    Request,
    urlopen,
)


class OpenAICompatibleProvider:
    """
    Minimal client for OpenAI-compatible chat-completion APIs.

    ClaimGraph uses this adapter for different inference runtimes:

    - NVIDIA NIM
    - vLLM
    - Meta-compatible endpoints
    - OpenAI

    Provider-specific behaviour is configuration, not graph logic.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        model_name: str,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
        max_tokens: int = 2048,
        temperature: float | None = 0.0,
        prepend_no_think: bool = False,
        use_json_response_format: bool = True,
        token_limit_field: str = "max_tokens",
    ):
        if token_limit_field not in {
            "max_tokens",
            "max_completion_tokens",
        }:
            raise ValueError(
                "Unsupported token limit field: "
                f"{token_limit_field}"
            )

        self.provider_name = provider_name
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")

        self.api_key = api_key

        self.timeout_seconds = (
            timeout_seconds
        )

        self.max_tokens = max_tokens

        self.temperature = temperature

        self.prepend_no_think = (
            prepend_no_think
        )

        self.use_json_response_format = (
            use_json_response_format
        )

        self.token_limit_field = (
            token_limit_field
        )


    def complete_json(
        self,
        *,
        system: str,
        user: str,
        reasoning: bool = False,
    ) -> dict[str, Any]:

        system_content = system


        # Nemotron-specific behaviour.
        #
        # Do NOT send /no_think to OpenAI,
        # Apertus, Meta, etc.
        if (
            self.prepend_no_think
            and not reasoning
        ):
            system_content = (
                "/no_think\n\n"
                + system_content
            )


        payload: dict[str, Any] = {
            "model":
                self.model_name,

            "messages": [
                {
                    "role": "system",
                    "content":
                        system_content,
                },
                {
                    "role": "user",
                    "content":
                        user,
                },
            ],
        }


        # Different OpenAI-compatible providers
        # use different token-limit field names.
        payload[
            self.token_limit_field
        ] = self.max_tokens


        if self.temperature is not None:
            payload["temperature"] = (
                self.temperature
            )


        if self.use_json_response_format:
            payload["response_format"] = {
                "type": "json_object",
            }


        headers = {
            "Content-Type":
                "application/json",
        }


        # Local NIM/vLLM can run without a key.
        # External providers generally use Bearer auth.
        if self.api_key:
            headers["Authorization"] = (
                f"Bearer {self.api_key}"
            )


        request = Request(
            (
                f"{self.base_url}/"
                "chat/completions"
            ),

            data=json.dumps(
                payload
            ).encode("utf-8"),

            headers=headers,

            method="POST",
        )


        with urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:

            result = json.load(
                response
            )


        try:
            choice = result[
                "choices"
            ][0]

            content = choice[
                "message"
            ]["content"]

            finish_reason = choice.get(
                "finish_reason"
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:

            raise ValueError(
                "Unexpected model response shape "
                f"from {self.provider_name}"
            ) from exc


        if finish_reason not in {
            None,
            "stop",
        }:
            raise ValueError(
                "Model did not complete cleanly: "
                f"finish_reason={finish_reason}"
            )


        parsed = json.loads(
            content
        )


        if not isinstance(
            parsed,
            dict,
        ):
            raise ValueError(
                "Model response must be "
                "a JSON object"
            )


        return parsed
