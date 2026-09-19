from __future__ import annotations

import os

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
)


class ModelTarget(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    id: str
    label: str

    provider: str
    model_name: str

    base_url: str

    api_key_env: str | None = None

    # Provider-specific compatibility settings.
    prepend_no_think: bool = False

    use_json_response_format: bool = True

    token_limit_field: Literal[
        "max_tokens",
        "max_completion_tokens",
    ] = "max_tokens"

    temperature: float | None = 0.0


MODEL_TARGETS: dict[
    str,
    ModelTarget,
] = {}


def _register(
    target: ModelTarget,
) -> None:
    MODEL_TARGETS[
        target.id
    ] = target


# =========================================================
# NVIDIA NIM / NEMOTRON
# =========================================================

_register(
    ModelTarget(
        id="nim-nemotron-super",

        label=(
            "NVIDIA NIM · "
            "Nemotron Super 49B"
        ),

        provider="nvidia-nim",

        model_name=(
            "nvidia/"
            "llama-3.3-nemotron-super-49b-v1.5"
        ),

        base_url=os.getenv(
            "NVIDIA_NIM_BASE_URL",
            "http://127.0.0.1:8000/v1",
        ),

        prepend_no_think=True,

        use_json_response_format=True,

        token_limit_field="max_tokens",

        temperature=0.0,
    )
)


# =========================================================
# APERTUS / vLLM
#
# Only expose it when you actually configure an endpoint.
# This prevents the UI from advertising a dead model.
# =========================================================

if os.getenv(
    "APERTUS_BASE_URL"
):
    _register(
        ModelTarget(
            id="apertus-vllm",

            label=(
                "Apertus · vLLM"
            ),

            provider="vllm",

            model_name=os.getenv(
                "APERTUS_MODEL",
                (
                    "swiss-ai/"
                    "Apertus-v1.1-4B-Instruct"
                ),
            ),

            base_url=os.environ[
                "APERTUS_BASE_URL"
            ],

            prepend_no_think=False,

            use_json_response_format=True,

            token_limit_field="max_tokens",

            temperature=0.0,
        )
    )


# =========================================================
# META
#
# Endpoint/model names are deliberately configuration,
# because these depend on your Meta API access.
# =========================================================

if (
    os.getenv("META_API_BASE_URL")
    and os.getenv("META_MODEL_NAME")
    and os.getenv("META_API_KEY")
):
    _register(
        ModelTarget(
            id="meta-api",

            label="Meta API",

            provider="meta",

            model_name=os.environ[
                "META_MODEL_NAME"
            ],

            base_url=os.environ[
                "META_API_BASE_URL"
            ],

            api_key_env=
                "META_API_KEY",

            prepend_no_think=False,

            # Start conservatively.
            # The prompt itself still requires JSON,
            # and ClaimGraph validates the result.
            use_json_response_format=False,

            token_limit_field="max_tokens",

            temperature=0.0,
        )
    )


# =========================================================
# OPENAI
# =========================================================

if os.getenv(
    "OPENAI_API_KEY"
):
    _register(
        ModelTarget(
            id="openai-gpt-5.6",

            label="OpenAI · GPT-5.6",

            provider="openai",

            model_name=os.getenv(
                "OPENAI_MODEL",
                "gpt-5.6",
            ),

            base_url=os.getenv(
                "OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            ),

            api_key_env=
                "OPENAI_API_KEY",

            prepend_no_think=False,

            use_json_response_format=True,

            token_limit_field=
                "max_completion_tokens",

            # Avoid imposing a sampling parameter
            # across model families unnecessarily.
            temperature=None,
        )
    )


def get_target(
    target_id: str,
) -> ModelTarget:

    try:
        return MODEL_TARGETS[
            target_id
        ]

    except KeyError as exc:
        raise ValueError(
            "Unknown model target: "
            f"{target_id}"
        ) from exc


def list_targets(
) -> list[ModelTarget]:

    return list(
        MODEL_TARGETS.values()
    )
