from __future__ import annotations

import json
import re
import threading
import time

from typing import Any

from urllib.error import HTTPError, URLError

from urllib.request import (
    Request,
    urlopen,
)


RATE_LIMIT_RETRIES = 4

# A shared gateway answers the same request in 3 seconds or
# not at all, so a short timeout retried beats a long one.
TIMEOUT_RETRIES = 1

RUNAWAY_TEMPERATURE = 0.4

# Below this many tokens left for the answer, a structured
# reply would be cut off anyway: the prompt is the problem.
MIN_OUTPUT_TOKENS = 256

# The server reports the prompt as "at least" so many tokens.
CONTEXT_MARGIN = 32

CONTEXT_LIMIT = re.compile(
    r"maximum context length is (\d+) tokens"
)

# vLLM words the prompt size two ways, depending on version:
# "your prompt contains at least 6145 input tokens" and
# "(6452 in the messages, 2048 in the completion)".
PROMPT_SIZE = re.compile(
    r"prompt contains at least (\d+) input tokens"
    r"|\((\d+) in the messages"
)


def output_budget(detail: str) -> int | None:
    """
    How many tokens are left for the answer, when a server
    refused a request for overflowing its context window.
    None when the refusal was about something else.

    Each retry asks for strictly fewer tokens than the one
    before, so a server that keeps refusing ends in an error,
    not a loop.
    """

    limit = CONTEXT_LIMIT.search(detail)
    prompt = PROMPT_SIZE.search(detail)

    if limit is None or prompt is None:
        return None

    return (
        int(limit.group(1))
        - int(prompt.group(1) or prompt.group(2))
        - CONTEXT_MARGIN
    )


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
    usage = None
    line = first

    while line:
        text = line.decode("utf-8", errors="replace").strip()
        line = response.readline()

        if not text.startswith("data:"):
            continue

        data = text[len("data:"):].strip()

        if data == "[DONE]":
            break

        chunk = json.loads(data)

        # With include_usage the token counts arrive in a final
        # chunk that has no choices.
        usage = chunk.get("usage") or usage
        choices = chunk.get("choices") or []

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
        ],
        "usage": usage,
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

      "none"
          Models without a reasoning mode, such as Apertus:
          nothing is sent, so nothing can be refused.

    JSON syntax is requested from the server, but
    semantic validation remains ClaimGraph's job.
    """

    # complete_json accepts `schema` and constrains decoding
    # with it. See provider.complete_structured.
    supports_json_schema = True

    THINKING_CONTROLS = (
        "system_prompt",
        "chat_template",
        "none",
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
        model_id: str | None = None,
        locality: str | None = None,
        extra_headers: dict[str, str] | None = None,
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

        # Which registry entry this is, and whether prompts
        # stay on our hardware. Both end up on every ModelRun.
        self.model_id = model_id
        self.locality = locality
        self.extra_headers = dict(extra_headers or {})

        # One provider serves many threads at once (claims are
        # extracted concurrently), so what the LAST call cost is
        # kept per thread.
        self._completion = threading.local()

    @property
    def last_completion(self) -> dict[str, Any]:
        """
        Execution metadata of this thread's latest answer:
        latency, finish reason and, where the server reports
        them, token counts. Usage is never estimated.
        """

        return dict(getattr(self._completion, "metadata", {}))

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        reasoning: bool = False,
        schema: dict[str, Any] | None = None,
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

            "response_format": (
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "answer",
                        "schema": schema,
                        "strict": True,
                    },
                }
                if schema is not None
                else {
                    "type": "json_object"
                }
            ),

            "temperature":
                self.temperature,

            "max_tokens":
                self.max_tokens,

            # See read_completion: makes the timeout an
            # idle timeout.
            "stream": True,

            # Token counts for the execution record. The first
            # thing given up if a server refuses it.
            "stream_options": {
                "include_usage": True,
            },
        }

        if self.thinking_control == "chat_template":
            payload["chat_template_kwargs"] = {
                "enable_thinking": reasoning,
            }

        headers = {
            "Content-Type":
                "application/json",
            **self.extra_headers,
        }

        self._completion.metadata = {}
        started = time.monotonic()

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

        self._completion.metadata = self._execution(
            result,
            finish_reason,
            started,
        )

        if finish_reason != "stop":
            raise ValueError(
                "Model did not complete cleanly: "
                f"finish_reason={finish_reason}"
            )

        return extract_json_object(
            content
        )

    def _execution(
        self,
        result: dict[str, Any],
        finish_reason: str | None,
        started: float,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "chosen_model_id": self.model_id,
            "locality": self.locality,
            # Lower than configured when the prompt left less
            # room in the context window.
            "max_tokens": getattr(
                self._completion,
                "max_tokens",
                self.max_tokens,
            ),
            "finish_reason": finish_reason,
            "latency_ms": round(
                (time.monotonic() - started) * 1000
            ),
        }

        usage = result.get("usage") or {}

        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            value = usage.get(key)

            if isinstance(value, int) and not isinstance(value, bool):
                metadata[key] = value

        return {
            key: value
            for key, value in metadata.items()
            if value is not None
        }

    @staticmethod
    def _give_something_up(
        payload: dict[str, Any],
    ) -> bool:
        """
        A server refused the request. Relax it one step, from
        the least to the most valuable thing we ask for:
        usage reporting and thinking control, then the schema
        (falling back to plain JSON mode), then JSON mode
        itself.
        """

        # Both are conveniences, and a refusal does not say which
        # field caused it: dropping them together costs one
        # round trip instead of two.
        optional = [
            key
            for key in ("stream_options", "chat_template_kwargs")
            if key in payload
        ]

        if optional:
            for key in optional:
                del payload[key]

            return True

        response_format = payload.get(
            "response_format"
        )

        if response_format is None:
            return False

        if response_format["type"] == "json_schema":
            payload["response_format"] = {
                "type": "json_object"
            }
        else:
            del payload["response_format"]

        return True

    def _post(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """
        Send the request, adapting to the server instead
        of failing on the first difference:

          400         prompt + max_tokens overflow the
                      context window: ask for fewer output
                      tokens, keeping everything else
          400 / 422   something optional was refused:
                      relax the request one step and try
                      again (see _give_something_up)
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
                    result = read_completion(
                        response
                    )

                self._completion.max_tokens = payload[
                    "max_tokens"
                ]

                return result

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

                # The body can only be read once.
                detail = error.read().decode(
                    "utf-8",
                    errors="replace",
                )

                budget = (
                    output_budget(detail)
                    if error.code == 400
                    else None
                )

                if budget is not None:
                    # Relaxing the format would not shrink the
                    # prompt, so an overflow never falls through
                    # to _give_something_up.
                    if (
                        budget < MIN_OUTPUT_TOKENS
                        or budget >= payload["max_tokens"]
                    ):
                        raise LLMTransportError(
                            "The prompt leaves no room for an "
                            f"answer in the model's context "
                            f"window: {detail[:300]}"
                        ) from error

                    payload["max_tokens"] = budget
                    continue

                if (
                    error.code in (400, 422)
                    and self._give_something_up(
                        payload
                    )
                ):
                    continue

                detail = detail[:300]

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
