from __future__ import annotations

import json

from typing import Any

from urllib.request import (
    Request,
    urlopen,
)


class OpenAICompatibleProvider:
    """
    Minimal OpenAI-compatible JSON client.

    For Nemotron, reasoning=False prepends /no_think.
    JSON syntax is requested from the server, but
    semantic validation remains ClaimGraph's job.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        reasoning: bool = False,
    ) -> dict[str, Any]:
        system_content = system

        if not reasoning:
            system_content = (
                "/no_think\n\n"
                + system_content
            )

        payload = {
            "model": self.model_name,

            "messages": [
                {
                    "role": "system",
                    "content": system_content,
                },
                {
                    "role": "user",
                    "content": user,
                },
            ],

            "response_format": {
                "type": "json_object"
            },

            "temperature":
                self.temperature,

            "max_tokens":
                self.max_tokens,
        }

        request = Request(
            (
                f"{self.base_url}/"
                "chat/completions"
            ),
            data=json.dumps(
                payload
            ).encode("utf-8"),
            headers={
                "Content-Type":
                    "application/json",
            },
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

            finish_reason = choice[
                "finish_reason"
            ]

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise ValueError(
                "Unexpected model response shape"
            ) from exc

        if finish_reason != "stop":
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
