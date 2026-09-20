"""Explicit inference configuration; no discovery or provisioning."""
import ipaddress
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

DEFAULT_MODELS = [{"provider": "nvidia-nim", "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5", "base_url": "http://127.0.0.1:8000/v1"}]

class RoutingError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

class Capabilities(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    no_think: bool = False
    json_object: bool = True

class ModelConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = ''
    label: str = ''
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_url: str
    roles: list[Literal['interaction', 'analysis', 'frontier']] = Field(default_factory=lambda: ['analysis'], min_length=1)
    locality: Literal['local', 'external'] | None = None
    max_tokens: int = Field(default=8192, gt=0, strict=True)
    capabilities: Capabilities | None = None
    auth_env: str | None = Field(default=None, pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    temperature: float = Field(default=0, ge=0, le=2)

    @model_validator(mode='after')
    def defaults(self):
        url = urlsplit(self.base_url)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('base_url must be an HTTP endpoint without credentials, query or fragment')
        try:
            local = ipaddress.ip_address(url.hostname).is_loopback
        except ValueError:
            local = url.hostname == 'localhost'
        self.locality = self.locality or ('local' if local else 'external')
        self.id = self.id or f'{self.provider}:{self.model}'
        self.label = self.label or self.model
        self.capabilities = self.capabilities or Capabilities(no_think=self.model == DEFAULT_MODELS[0]['model'])
        return self

    def public(self):
        return self.model_dump(include={'id', 'label', 'provider', 'model', 'roles', 'locality', 'max_tokens'})


def registry():
    raw = json.loads(os.environ.get('CLAIMGRAPH_MODELS', json.dumps(DEFAULT_MODELS)))
    if not isinstance(raw, list) or not raw:
        raise ValueError('CLAIMGRAPH_MODELS must be a nonempty JSON list')
    models = [ModelConfig.model_validate(m) for m in raw]
    if len({m.id for m in models}) != len(models):
        raise ValueError('Model IDs must be unique')
    return models


def resolve_model(models, selection):
    matches = [m for m in models if m.provider == selection.get('provider') and m.model == selection.get('model')]
    explicit = next((m for m in matches if m.id == selection.get('model_id', selection.get('id'))), None)
    if explicit:
        return explicit
    if len(matches) > 1:
        raise RoutingError('ambiguous_model', 'Select a configured model ID')
    return matches[0] if matches else None


def guard_egress(model):
    policy = os.environ.get('CLAIMGRAPH_EGRESS_POLICY', 'local_only')
    if policy not in ('local_only', 'external_allowed'):
        raise RoutingError('invalid_policy', 'Invalid CLAIMGRAPH_EGRESS_POLICY')
    if model.locality == 'external' and policy != 'external_allowed':
        raise RoutingError('egress_blocked', 'External inference is blocked by local_only policy')


def auth_headers(model):
    if not model.auth_env:
        return {}
    secret = os.environ.get(model.auth_env)
    if not secret:
        raise RoutingError('missing_auth', 'Configured inference authentication is missing')
    return {'Authorization': f'Bearer {secret}'}


def available(model):
    try:
        guard_egress(model)
        with urlopen(Request(model.base_url.rstrip('/') + '/models', headers=auth_headers(model)), timeout=2) as response:
            payload = json.load(response)
        return any(item.get('id') == model.model for item in payload.get('data', []))
    except Exception:
        return False


def make_provider(model, *, route='analysis'):
    from .openai_compatible import OpenAICompatibleProvider
    guard_egress(model)
    auth_headers(model)
    return OpenAICompatibleProvider(provider_name=model.provider, model_name=model.model,
        base_url=model.base_url, max_tokens=model.max_tokens, no_think=model.capabilities.no_think,
        json_object=model.capabilities.json_object, auth_env=model.auth_env,
        timeout_seconds=model.timeout_seconds, temperature=model.temperature,
        locality=model.locality, model_id=model.id, route=route)
