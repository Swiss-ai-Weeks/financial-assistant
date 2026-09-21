"""
The models the desk can ask, and where each one runs.

One investigation is explained by exactly one model, chosen
per run. Running the same anomaly through two of them and
laying the ClaimGraphs side by side is the point: where
Nemotron and Apertus agree, the explanation does not depend
on who was asked.

Nothing here discovers or provisions an endpoint. A model
exists because it was configured; whether it is reachable is
probed, cached for a few seconds, and reported.
"""

from __future__ import annotations

import ipaddress
import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .openai_compatible import OpenAICompatibleProvider
from .provider import StructuredLLM


HEALTH_CACHE_SECONDS = 10
HEALTH_TIMEOUT_SECONDS = 2.5

Role = Literal["analysis", "interaction", "frontier"]


# Apertus is the Swiss AI Initiative's fully open model (EPFL,
# ETH Zurich, CSCS): open weights, open training data, no
# reasoning mode. One word (APERTUS_PROFILE) decides where it
# runs, exactly like LLM_PROFILE does for Nemotron.
#
#   local    vLLM on our own GPUs, started with `make apertus`
#            (port 8001, next to Nemotron on 8000)
#   hosted   an OpenAI-compatible gateway; needs APERTUS_API_KEY.
#            The default is the Public AI Inference Utility.
#            Any other host works through APERTUS_BASE_URL and
#            APERTUS_MODEL (Hugging Face router, Azure, ...).
#   off      not offered
APERTUS_PROFILES = {
    "local": {
        "provider": "vllm-local",
        "base_url": "http://127.0.0.1:8001/v1",
        "model": "swiss-ai/Apertus-8B-Instruct-2509",
        "workers": "8",
        "timeout": "120",
    },
    "hosted": {
        "provider": "publicai",
        "base_url": "https://api.publicai.co/v1",
        "model": "swiss-ai/apertus-70b-instruct",
        "workers": "3",
        "timeout": "180",
    },
}


class RoutingError(ValueError):
    """
    A model could not be used, for a reason the desk can name
    (`code`) rather than a transport failure.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def is_local_url(base_url: str) -> bool:
    """
    Whether prompts sent to this endpoint stay on hardware we
    control: loopback, a private address, or a bare hostname
    on our own network.
    """

    host = urlparse(base_url).hostname or ""

    if host == "localhost" or "." not in host:
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    return address.is_loopback or address.is_private


class ModelSpec(BaseModel):
    """One configured model. Holds no secret, only its name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    label: str = ""
    origin: str = ""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_url: str

    # Name of the environment variable holding the key, never
    # the key: a spec is listed to the browser.
    api_key_env: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )

    thinking_control: Literal["system_prompt", "chat_template", "none"] = "none"
    roles: tuple[Role, ...] = ("analysis", "interaction")

    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    workers: int = Field(default=4, ge=1, le=64)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @field_validator("base_url")
    @classmethod
    def _plain_http_endpoint(cls, value: str) -> str:
        url = urlparse(value)

        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "base_url must be an HTTP endpoint without "
                "credentials, query or fragment"
            )

        return value.rstrip("/")

    @property
    def is_local(self) -> bool:
        return is_local_url(self.base_url)

    @property
    def locality(self) -> str:
        return "local" if self.is_local else "external"

    @property
    def display_name(self) -> str:
        return self.label or self.model.split("/")[-1]


@dataclass(frozen=True)
class ModelHealth:
    online: bool
    detail: str = ""


def probe(
    spec: ModelSpec,
    api_key: str | None,
    *,
    opener=urlopen,
) -> ModelHealth:
    """Ask the endpoint which models it serves."""

    # A hosted gateway lists its models to anyone, so without
    # this check it would look online and then answer every
    # real request with 401.
    if not spec.is_local and not api_key:
        return ModelHealth(
            online=False,
            detail=(
                f"{spec.api_key_env or 'an API key'} is not set "
                "for the hosted endpoint"
            ),
        )

    headers = {"User-Agent": "Pythia/0.4"}

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        request = Request(f"{spec.base_url}/models", headers=headers)

        with opener(request, timeout=HEALTH_TIMEOUT_SECONDS) as response:
            served = [
                entry.get("id")
                for entry in json.load(response).get("data", [])
            ]

    except Exception:
        return ModelHealth(
            online=False,
            detail=f"{spec.base_url} is not reachable",
        )

    if served and spec.model not in served:
        # vLLM serves exactly what it was started with: a
        # different name means requests would be refused.
        if spec.is_local:
            return ModelHealth(
                online=False,
                detail=f"serving {', '.join(map(str, served))}, not {spec.model}",
            )

    return ModelHealth(online=True, detail=f"serving {spec.model}")


class ModelRegistry:
    """
    Configured models, their providers and their health.

    `factories` lets a caller (tests, or a desk wired to a
    single legacy model) supply the client for a model id
    instead of having one built from its spec. Health is
    probed either way: a factory says how to talk to a model,
    not that it is listening.
    """

    def __init__(
        self,
        specs: tuple[ModelSpec, ...],
        *,
        default_id: str | None = None,
        egress_policy: str = "external_allowed",
        environ: Mapping[str, str] | None = None,
        factories: Mapping[str, Callable[[], StructuredLLM]] | None = None,
        prober: Callable[[ModelSpec, str | None], ModelHealth] = probe,
    ):
        if not specs:
            raise ValueError("At least one model must be configured.")

        ids = [spec.id for spec in specs]

        if len(ids) != len(set(ids)):
            raise ValueError("Model ids must be unique.")

        if egress_policy not in ("local_only", "external_allowed"):
            raise ValueError(
                "LLM_EGRESS_POLICY must be local_only or external_allowed"
            )

        self._specs = {spec.id: spec for spec in specs}
        self._default_id = default_id or ids[0]

        if self._default_id not in self._specs:
            raise ValueError(f"Unknown default model {self._default_id!r}.")

        self._egress_policy = egress_policy
        self._environ = environ if environ is not None else os.environ
        self._factories = dict(factories or {})
        self._probe = prober

        self._lock = threading.Lock()
        self._health: dict[str, tuple[float, ModelHealth]] = {}

    # -------------------------------------------------

    @property
    def default_id(self) -> str:
        return self._default_id

    @property
    def egress_policy(self) -> str:
        return self._egress_policy

    def list(self) -> tuple[ModelSpec, ...]:
        return tuple(self._specs.values())

    def get(self, model_id: str | None = None) -> ModelSpec:
        spec = self._specs.get(model_id or self._default_id)

        if spec is None:
            raise RoutingError(
                "unknown_model",
                f"No model is configured as {model_id!r}.",
            )

        return spec

    def with_role(self, role: Role) -> tuple[ModelSpec, ...]:
        return tuple(s for s in self._specs.values() if role in s.roles)

    def api_key(self, spec: ModelSpec) -> str | None:
        if not spec.api_key_env:
            return None

        return self._environ.get(spec.api_key_env) or None

    # -------------------------------------------------

    def blocked(self, spec: ModelSpec) -> str | None:
        """Why policy forbids this model, if it does."""

        if not spec.is_local and self._egress_policy == "local_only":
            return (
                "External inference is blocked: LLM_EGRESS_POLICY "
                "is local_only, so prompts may not leave this machine."
            )

        return None

    def health(self, model_id: str | None = None) -> ModelHealth:
        spec = self.get(model_id)

        if (reason := self.blocked(spec)) is not None:
            return ModelHealth(online=False, detail=reason)

        with self._lock:
            cached = self._health.get(spec.id)

            if (
                cached is not None
                and time.time() - cached[0] < HEALTH_CACHE_SECONDS
            ):
                return cached[1]

        health = self._probe(spec, self.api_key(spec))

        with self._lock:
            self._health[spec.id] = (time.time(), health)

        return health

    def provider(self, model_id: str | None = None) -> StructuredLLM:
        spec = self.get(model_id)

        if (reason := self.blocked(spec)) is not None:
            raise RoutingError("egress_blocked", reason)

        if spec.id in self._factories:
            return self._factories[spec.id]()

        api_key = self.api_key(spec)

        if spec.api_key_env and not api_key and not spec.is_local:
            raise RoutingError(
                "missing_auth",
                f"{spec.api_key_env} is not set.",
            )

        return OpenAICompatibleProvider(
            provider_name=spec.provider,
            model_name=spec.model,
            base_url=spec.base_url,
            api_key=api_key,
            thinking_control=spec.thinking_control,
            max_tokens=spec.max_tokens,
            timeout_seconds=spec.timeout_seconds,
            temperature=spec.temperature,
            model_id=spec.id,
            locality=spec.locality,
            # Some public gateways refuse the default
            # Python-urllib agent outright.
            extra_headers={"User-Agent": "Pythia/0.4"},
        )


# -----------------------------------------------------
# Configuration
# -----------------------------------------------------


def apertus_spec(environ: Mapping[str, str]) -> ModelSpec | None:
    """
    The Apertus entry selected by APERTUS_PROFILE.

    Unset, the profile follows the key: with APERTUS_API_KEY the
    hosted gateway, without it the local vLLM port. Either way
    the model is listed, and shown as offline until it answers.
    """

    env = environ.get

    profile_name = (
        env("APERTUS_PROFILE")
        or ("hosted" if env("APERTUS_API_KEY") else "local")
    ).strip().lower()

    if profile_name == "off":
        return None

    if profile_name not in APERTUS_PROFILES:
        raise ValueError(
            f"APERTUS_PROFILE must be one of "
            f"{sorted((*APERTUS_PROFILES, 'off'))}, not {profile_name!r}"
        )

    profile = APERTUS_PROFILES[profile_name]
    model = env("APERTUS_MODEL") or profile["model"]

    return ModelSpec(
        id="apertus",
        label="Apertus " + ("70B" if "70b" in model.lower() else "8B" if "8b" in model.lower() else ""),
        origin="Swiss AI Initiative · EPFL, ETH Zurich, CSCS",
        provider=env("APERTUS_PROVIDER") or profile["provider"],
        model=model,
        base_url=env("APERTUS_BASE_URL") or profile["base_url"],
        api_key_env="APERTUS_API_KEY",
        thinking_control="none",
        max_tokens=int(env("APERTUS_MAX_TOKENS") or env("LLM_MAX_TOKENS") or "2048"),
        timeout_seconds=float(env("APERTUS_TIMEOUT_SECONDS") or profile["timeout"]),
        workers=int(env("APERTUS_WORKERS") or profile["workers"]),
    )


def extra_specs(environ: Mapping[str, str]) -> tuple[ModelSpec, ...]:
    """
    Further models from PYTHIA_MODELS, a JSON list of ModelSpec
    objects. This is how a comparison model (roles:
    ["frontier"]) or a second local endpoint is added without
    touching code.
    """

    raw = environ.get("PYTHIA_MODELS")

    if not raw:
        return ()

    try:
        entries = json.loads(raw)
    except ValueError as error:
        raise ValueError("PYTHIA_MODELS must be a JSON list.") from error

    if not isinstance(entries, list):
        raise ValueError("PYTHIA_MODELS must be a JSON list.")

    return tuple(ModelSpec.model_validate(entry) for entry in entries)


def build_registry(
    default: ModelSpec,
    *,
    environ: Mapping[str, str] | None = None,
    factories: Mapping[str, Callable[[], StructuredLLM]] | None = None,
) -> ModelRegistry:
    """
    The desk's registry: the LLM_PROFILE model first (it stays
    the default), then Apertus, then anything in PYTHIA_MODELS.
    A later entry with an id already taken replaces the earlier.
    """

    environ = environ if environ is not None else os.environ

    specs: dict[str, ModelSpec] = {default.id: default}

    if (apertus := apertus_spec(environ)) is not None:
        specs[apertus.id] = apertus

    for spec in extra_specs(environ):
        specs[spec.id] = spec

    return ModelRegistry(
        tuple(specs.values()),
        default_id=environ.get("LLM_DEFAULT_MODEL") or default.id,
        egress_policy=(
            environ.get("LLM_EGRESS_POLICY") or "external_allowed"
        ).strip().lower(),
        environ=environ,
        factories=factories,
    )
