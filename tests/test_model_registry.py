import pytest

from financial_assistant.llm.model_registry import (
    ModelHealth,
    ModelRegistry,
    ModelSpec,
    RoutingError,
    apertus_spec,
    build_registry,
)
from financial_assistant.copilot import CopilotService, requested_route


NEMOTRON = ModelSpec(
    id="nemotron",
    provider="vllm-local",
    model="nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
    base_url="http://127.0.0.1:8000/v1",
    api_key_env="LLM_API_KEY",
    thinking_control="chat_template",
)

ONLINE = lambda spec, key: ModelHealth(online=True)  # noqa: E731


def test_apertus_is_offered_next_to_the_profile_model():
    registry = build_registry(NEMOTRON, environ={})

    assert [spec.id for spec in registry.list()] == ["nemotron", "apertus"]
    assert registry.default_id == "nemotron"

    apertus = registry.get("apertus")

    # Without a key it is the copy served on our own GPUs.
    assert apertus.is_local
    assert apertus.base_url == "http://127.0.0.1:8001/v1"
    assert "Apertus-8B" in apertus.model
    # Apertus has no reasoning mode: nothing is sent to switch off.
    assert apertus.thinking_control == "none"
    assert "Swiss AI" in apertus.origin


def test_a_key_selects_the_hosted_apertus_and_one_word_overrides_it():
    hosted = apertus_spec({"APERTUS_API_KEY": "secret"})

    assert not hosted.is_local
    assert "70b" in hosted.model.lower()
    # The spec names the variable, never the key.
    assert "secret" not in hosted.model_dump_json()

    local = apertus_spec({"APERTUS_API_KEY": "secret", "APERTUS_PROFILE": "local"})

    assert local.is_local

    assert apertus_spec({"APERTUS_PROFILE": "off"}) is None

    with pytest.raises(ValueError, match="APERTUS_PROFILE"):
        apertus_spec({"APERTUS_PROFILE": "cloud"})


def test_more_models_come_from_one_json_variable():
    registry = build_registry(
        NEMOTRON,
        environ={
            "APERTUS_PROFILE": "off",
            "PYTHIA_MODELS": (
                '[{"id": "frontier", "provider": "x", "model": "big", '
                '"base_url": "https://api.example.com/v1", '
                '"api_key_env": "X_KEY", "roles": ["frontier"]}]'
            ),
        },
    )

    assert [spec.id for spec in registry.list()] == ["nemotron", "frontier"]

    with pytest.raises(ValueError):
        build_registry(NEMOTRON, environ={"PYTHIA_MODELS": "{}"})


def test_local_only_policy_keeps_prompts_on_the_machine():
    registry = build_registry(
        NEMOTRON,
        environ={"APERTUS_API_KEY": "k", "LLM_EGRESS_POLICY": "local_only"},
    )

    assert not registry.health("apertus").online
    assert "local_only" in registry.health("apertus").detail

    with pytest.raises(RoutingError) as refused:
        registry.provider("apertus")

    assert refused.value.code == "egress_blocked"

    # The local model is unaffected.
    assert registry.provider("nemotron").model_id == "nemotron"


def test_a_hosted_model_without_its_key_is_offline_not_broken():
    registry = build_registry(NEMOTRON, environ={"APERTUS_PROFILE": "hosted"})

    health = registry.health("apertus")

    assert not health.online
    assert "APERTUS_API_KEY" in health.detail


def test_the_provider_is_built_from_the_spec():
    registry = build_registry(NEMOTRON, environ={"APERTUS_API_KEY": "k"})
    provider = registry.provider("apertus")

    assert provider.thinking_control == "none"
    assert provider.api_key == "k"
    assert provider.locality == "external"
    assert provider.model_id == "apertus"


def test_frontier_is_never_a_fallback():
    assert requested_route("What am I looking at?") == ("interaction", False)
    # Asking for a judgement is analysis, whatever plane is selected.
    assert requested_route("Is this hypothesis plausible?")[0] == "analysis"
    assert requested_route("Please reassess the second hypothesis")[0] == "analysis"
    assert requested_route("frontier second opinion") == ("frontier", True)
    assert requested_route("anything", "frontier") == ("frontier", True)

    frontier = ModelSpec(
        id="frontier",
        provider="x",
        model="big",
        base_url="https://api.example.com/v1",
        api_key_env="X_KEY",
        roles=("frontier",),
    )

    service = CopilotService(
        ModelRegistry(
            (NEMOTRON, frontier),
            environ={"X_KEY": "k"},
            prober=ONLINE,
        )
    )

    assert service.route("interaction", None, explicit=False).id == "nemotron"
    assert service.route("analysis", "nemotron", explicit=False).id == "nemotron"
    assert service.route("frontier", None, explicit=True).id == "frontier"

    with pytest.raises(RoutingError) as refused:
        service.route("frontier", None, explicit=False)

    assert refused.value.code == "explicit_required"

    # A model offered only for comparison never runs analysis.
    with pytest.raises(RoutingError):
        service.route("analysis", "frontier", explicit=False)
