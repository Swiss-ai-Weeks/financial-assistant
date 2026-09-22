import io
import json
from urllib.error import HTTPError

import pytest

from financial_assistant.llm import LLMTransportError, OpenAICompatibleProvider
from financial_assistant.llm import openai_compatible as module
from financial_assistant.llm.openai_compatible import (
    extract_json_object,
    read_completion,
)


class FakeEndpoint:
    """Replays scripted answers and records what was sent."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(
            {"headers": dict(request.header_items()), **json.loads(request.data)}
        )

        answer = self.answers.pop(0)

        if answer is TimeoutError:
            raise TimeoutError("The read operation timed out")

        if isinstance(answer, int):
            answer = HTTPError(
                request.full_url, answer, "refused", {}, io.BytesIO(b'{"detail": "no"}')
            )

        if isinstance(answer, HTTPError):
            raise answer

        finish = "stop"

        if isinstance(answer, tuple):
            answer, finish = answer

        body = {
            "choices": [{"message": {"content": answer}, "finish_reason": finish}]
        }

        return io.BytesIO(json.dumps(body).encode())


@pytest.fixture()
def endpoint(monkeypatch):
    def install(*answers):
        fake = FakeEndpoint(*answers)

        monkeypatch.setattr(module, "urlopen", fake)
        monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

        return fake

    return install


def provider(**overrides):
    return OpenAICompatibleProvider(
        provider_name="test",
        model_name="nvidia/nemotron-3.5-lightning-30b-a3b",
        base_url="https://llm.example.com/v1",
        **{"thinking_control": "chat_template", **overrides},
    )


def test_request_carries_key_json_mode_and_thinking_switch(endpoint):
    fake = endpoint('{"ok": true}')

    assert provider(api_key="nvapi-secret").complete_json(system="s", user="u") == {
        "ok": True
    }

    sent = fake.requests[0]

    assert sent["headers"]["Authorization"] == "Bearer nvapi-secret"
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}


def test_a_refused_request_is_relaxed_one_step_at_a_time(endpoint):
    # The server refuses the thinking switch, then the schema,
    # then JSON mode, then answers in a code fence after
    # thinking out loud.
    fake = endpoint(
        400,
        422,
        400,
        '<think>Let me see.</think>\n```json\n{"verdict": "no_event"}\n```',
    )

    answer = provider().complete_json(
        system="s", user="u", schema={"type": "object"}
    )

    assert answer == {"verdict": "no_event"}

    formats = [r.get("response_format", {}).get("type") for r in fake.requests]

    # Least valuable first: thinking control, schema, JSON mode.
    assert "chat_template_kwargs" in fake.requests[0]
    assert all("chat_template_kwargs" not in r for r in fake.requests[1:])
    assert formats == ["json_schema", "json_schema", "json_object", None]


def test_the_schema_is_handed_to_the_decoder(endpoint):
    from pydantic import BaseModel

    from financial_assistant.llm.provider import complete_structured

    class Answer(BaseModel):
        verdict: str

    fake = endpoint('{"verdict": "no_event"}')

    complete_structured(provider(), system="s", user="u", response_model=Answer)

    sent = fake.requests[0]["response_format"]

    assert sent["type"] == "json_schema"
    assert sent["json_schema"]["strict"] is True
    assert sent["json_schema"]["schema"]["required"] == ["verdict"]


def test_providers_without_schema_support_get_the_plain_request():
    from pydantic import BaseModel

    from financial_assistant.llm.provider import complete_structured

    class Answer(BaseModel):
        verdict: str

    class Plain:
        provider_name = "fake"
        model_name = "fake-model"

        def complete_json(self, *, system, user, reasoning=False):
            return {"verdict": "ok"}

    # Would raise TypeError if `schema` were passed.
    assert complete_structured(
        Plain(), system="s", user="u", response_model=Answer
    ) == {"verdict": "ok"}


def test_rate_limits_are_waited_out(endpoint):
    fake = endpoint(429, 429, '{"ok": true}')

    assert provider().complete_json(system="s", user="u") == {"ok": True}
    assert len(fake.requests) == 3

    # Nothing was given up: the server never refused a field.
    assert "response_format" in fake.requests[-1]


def test_other_errors_surface_with_the_servers_explanation(endpoint):
    endpoint(401)

    with pytest.raises(LLMTransportError, match="HTTP 401"):
        provider().complete_json(system="s", user="u")


def test_a_slow_gateway_is_retried_before_giving_up(endpoint):
    fake = endpoint(TimeoutError, '{"ok": true}')

    assert provider().complete_json(system="s", user="u") == {"ok": True}
    assert len(fake.requests) == 2

    endpoint(TimeoutError, TimeoutError)

    # An outage is not a bad answer: callers tell them apart.
    with pytest.raises(LLMTransportError, match="did not answer"):
        provider().complete_json(system="s", user="u")


def test_only_the_wrapping_is_forgiven_never_the_content():
    assert extract_json_object('Here you go: {"a": 1} Hope it helps.') == {"a": 1}
    assert extract_json_object('<think>{"decoy": 1}</think>{"a": 2}') == {"a": 2}

    with pytest.raises(ValueError):
        extract_json_object("[1, 2, 3]")

    with pytest.raises(ValueError):
        extract_json_object("I could not decide.")


def sse(*events):
    return io.BytesIO(
        "".join(f"data: {event}\n\n" for event in events).encode()
    )


def test_a_streamed_answer_is_assembled_from_its_pieces():
    def delta(text=None, finish=None):
        return json.dumps(
            {"choices": [{"delta": {"content": text}, "finish_reason": finish}]}
        )

    result = read_completion(
        sse(
            delta(""),
            delta('{"verdict": '),
            delta('"no_event"}'),
            delta(finish="stop"),
            # Usage-only chunk some servers append.
            json.dumps({"choices": [], "usage": {"completion_tokens": 9}}),
            "[DONE]",
        )
    )

    choice = result["choices"][0]

    assert choice["message"]["content"] == '{"verdict": "no_event"}'
    assert choice["finish_reason"] == "stop"


def test_a_server_that_ignores_streaming_is_still_understood():
    body = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}

    assert read_completion(io.BytesIO(json.dumps(body).encode())) == body
    assert read_completion(io.BytesIO(b"\n" + json.dumps(body, indent=2).encode())) == body


def test_requests_ask_for_a_stream(endpoint):
    fake = endpoint('{"ok": true}')
    provider().complete_json(system="s", user="u")

    assert fake.requests[0]["stream"] is True


def test_a_runaway_answer_gets_one_nudge(endpoint):
    fake = endpoint(('{"hypotheses": [', "length"), '{"ok": true}')

    assert provider().complete_json(system="s", user="u") == {"ok": True}

    first, second = fake.requests

    assert first["temperature"] == 0.0
    assert second["temperature"] > 0

    endpoint(("{", "length"), ("{", "length"))

    with pytest.raises(ValueError, match="finish_reason=length"):
        provider().complete_json(system="s", user="u")


def overflow(prompt_tokens, context=8192, requested=2048):
    """vLLM's refusal of a prompt too long for its context window."""

    message = (
        f"This model's maximum context length is {context} tokens. "
        f"However, you requested {requested} output tokens and your "
        f"prompt contains at least {prompt_tokens} input tokens, for a "
        f"total of at least {prompt_tokens + requested} tokens."
    )

    return HTTPError(
        "http://llm", 400, "Bad Request", {},
        io.BytesIO(json.dumps({"error": {"message": message}}).encode()),
    )


def test_a_context_overflow_asks_for_fewer_output_tokens(endpoint):
    fake = endpoint(overflow(6145), '{"ok": true}')

    llm = provider()
    answer = llm.complete_json(system="s", user="u", schema={"type": "object"})

    assert answer == {"ok": True}

    # Only the output budget shrinks; nothing else is given up.
    assert [r["max_tokens"] for r in fake.requests] == [2048, 8192 - 6145 - 32]
    assert fake.requests[1]["response_format"]["type"] == "json_schema"
    assert "chat_template_kwargs" in fake.requests[1]

    assert llm.last_completion["max_tokens"] == 8192 - 6145 - 32


def test_a_prompt_that_fills_the_context_is_reported_not_relaxed(endpoint):
    fake = endpoint(overflow(8100))

    with pytest.raises(LLMTransportError, match="no room for an answer"):
        provider().complete_json(system="s", user="u")

    assert len(fake.requests) == 1
