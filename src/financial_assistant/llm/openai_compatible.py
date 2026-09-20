from __future__ import annotations

import json
import re
import time

from typing import Any

from urllib.error import HTTPError, URLError

from urllib.request import (
    Request,
    urlopen,
)


# Optional request fields, in the order they are given up
# when a server refuses the request. Self-hosted vLLM takes
# all of them; hosted gateways differ in which they accept.
OPTIONAL_FIELDS = (
    "chat_template_kwargs",
    "response_format",
)

RATE_LIMIT_RETRIES = 4

# A shared gateway answers the same request in 3 seconds or
# not at all, so a short timeout retried beats a long one.
TIMEOUT_RETRIES = 1

RUNAWAY_TEMPERATURE = 0.4


class LLMTransportError(RuntimeError):
    """
    The model could not be reached or did not answer.

    Distinct from ValueError, which means it answered and the
    answer was not acceptable. Callers report the two very
    differently: one is an outage, the other is the model.
    """


def read_completion(response) -> dict[str, Any]:
    """
    Read a chat completion, streamed or not, into the shape
    of a non-streamed one.

    Requests are streamed so that, where the server streams,
    the socket timeout measures SILENCE rather than total
    duration: a long answer keeps arriving and is never cut
    off, while a hung request is detected quickly.

    Not every server does. Measured on NVIDIA's hosted
    gateway, a JSON-mode answer is buffered and delivered as
    one chunk at the end, so there the timeout still has to
    cover the whole generation. A server that ignores
    `stream` and answers with one JSON body is read as such.
    """

    first = response.readline()

    while first and not first.strip():
        first = response.readline()

    if not first.lstrip().startswith(b"data:"):
        return json.loads(first + response.read())

    content: list[str] = []
    finish_reason = None
    line = first

    while line:
        text = line.decode("utf-8", errors="replace").strip()
        line = response.readline()

        if not text.startswith("data:"):
            continue

        data = text[len("data:"):].strip()

        if data == "[DONE]":
            break

        choices = json.loads(data).get("choices") or []

        if not choices:
            continue

        piece = (choices[0].get("delta") or {}).get("content")

        if piece:
            content.append(piece)

        finish_reason = choices[0].get("finish_reason") or finish_reason

    return {
        "choices": [
            {
                "message": {"content": "".join(content)},
                "finish_reason": finish_reason,
            }
        ]
    }


def extract_json_object(content: str) -> dict[str, Any]:
    """
    Read the JSON object out of a model reply.

    With JSON mode the reply IS the object. Without it (a
    server that refused response_format, or one that did
    not switch thinking off) the object can arrive after a
    <think> block or inside a code fence. Only the wrapping
    is removed: whatever is inside must still be one valid
    JSON object, and its meaning is validated by the caller.
    """

    text = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.DOTALL,
    ).strip()

    fenced = re.search(
        r"```(?:json)?\s*(\{.*\})\s*```",
        text,
        flags=re.DOTALL,
    )

    if fenced:
        text = fenced.group(1)

    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")

        if start != -1 and end > start:
            text = text[start:end + 1]

    parsed = json.loads(text)

    if not isinstance(parsed, dict):
        raise ValueError(
            "Model response must be "
            "a JSON object"
        )

    return parsed


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

            # See read_completion: makes the timeout an
            # idle timeout.
            "stream": True,
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

        # At temperature 0 a model that starts repeating
        # itself never stops, and the answer runs to the token
        # limit. A little randomness breaks the loop, so that
        # case gets exactly one second attempt.
        for attempt_temperature in (
            self.temperature,
            max(self.temperature, RUNAWAY_TEMPERATURE),
        ):
            payload["temperature"] = attempt_temperature

            result = self._post(
                payload,
                headers,
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

            if finish_reason != "length":
                break

        if finish_reason != "stop":
            raise ValueError(
                "Model did not complete cleanly: "
                f"finish_reason={finish_reason}"
            )

        return extract_json_object(
            content
        )

    def _post(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """
        Send the request, adapting to the server instead
        of failing on the first difference:

          400 / 422   an optional field was refused: give
                      one up and try again, thinking
                      control first, JSON mode last
          429         rate limited: wait and try again
        """

        payload = dict(payload)
        rate_limited = 0
        timed_out = 0

        while True:
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

            try:
                with urlopen(
                    request,
                    timeout=self.timeout_seconds,
                ) as response:
                    return read_completion(
                        response
                    )

            except HTTPError as error:
                if (
                    error.code == 429
                    and rate_limited
                    < RATE_LIMIT_RETRIES
                ):
                    rate_limited += 1
                    time.sleep(
                        2.0 * rate_limited
                    )
                    continue

                refused = next(
                    (
                        field
                        for field in OPTIONAL_FIELDS
                        if field in payload
                    ),
                    None,
                )

                if (
                    error.code in (400, 422)
                    and refused is not None
                ):
                    del payload[refused]
                    continue

                detail = error.read().decode(
                    "utf-8",
                    errors="replace",
                )[:300]

                raise LLMTransportError(
                    f"Model endpoint answered HTTP "
                    f"{error.code}: {detail}"
                ) from error

            except (
                TimeoutError,
                URLError,
                ConnectionError,
            ) as error:
                if timed_out < TIMEOUT_RETRIES:
                    timed_out += 1
                    continue

                raise LLMTransportError(
                    "Model endpoint did not answer after "
                    f"{timed_out + 1} attempts: {error}"
                ) from error
