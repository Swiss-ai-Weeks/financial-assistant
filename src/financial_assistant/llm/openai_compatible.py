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

    Reasoning is switched off per request unless the
    caller asks for it. Nemotron generations disagree
    on how that is expressed:

      "system_prompt"
          Llama-Nemotron: /no_think in the system turn.

      "chat_template"
          Nemotron 3 / 3.5: enable_thinking passed as a
          chat-template kwarg.

    JSON syntax is requested from the server, but
    semantic validation remains ClaimGraph's job.
    """

    THINKING_CONTROLS = (
        "system_prompt",
        "chat_template",
    )

    def __init__(
        self,
        *,
        provider_name: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        api_key: str | None = None,
        thinking_control: str = "system_prompt",
    ):
        if (
            thinking_control
            not in self.THINKING_CONTROLS
        ):
            raise ValueError(
                "thinking_control must be one of "
                f"{self.THINKING_CONTROLS}"
            )

        self.api_key = api_key
        self.thinking_control = thinking_control

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

        if (
            not reasoning
            and self.thinking_control
            == "system_prompt"
        ):
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

        if self.thinking_control == "chat_template":
            payload["chat_template_kwargs"] = {
                "enable_thinking": reasoning,
            }

        headers = {
            "Content-Type":
                "application/json",
        }

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
