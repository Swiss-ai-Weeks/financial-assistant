import io
import json
from urllib.error import HTTPError

import pytest

from financial_assistant.llm import LLMTransportError, OpenAICompatibleProvider
from financial_assistant.llm import openai_compatible as module
from financial_assistant.llm.openai_compatible import extract_json_object


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
            raise HTTPError(
                request.full_url, answer, "refused", {}, io.BytesIO(b'{"detail": "no"}')
            )

        body = {
            "choices": [{"message": {"content": answer}, "finish_reason": "stop"}]
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


def test_refused_fields_are_given_up_one_at_a_time(endpoint):
    # The gateway refuses the thinking switch, then JSON mode,
    # then answers in a code fence after thinking out loud.
    fake = endpoint(
        400,
        422,
        '<think>Let me see.</think>\n```json\n{"verdict": "no_event"}\n```',
    )

    assert provider().complete_json(system="s", user="u") == {"verdict": "no_event"}

    first, second, third = fake.requests

    assert "chat_template_kwargs" in first and "response_format" in first
    assert "chat_template_kwargs" not in second and "response_format" in second
    assert "chat_template_kwargs" not in third and "response_format" not in third


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
    fake = endpoint(TimeoutError, TimeoutError, '{"ok": true}')

    assert provider().complete_json(system="s", user="u") == {"ok": True}
    assert len(fake.requests) == 3

    endpoint(TimeoutError, TimeoutError, TimeoutError)

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
