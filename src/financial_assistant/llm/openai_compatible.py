from __future__ import annotations
import json
import os
import time
from threading import local
from urllib.request import Request, urlopen


class OpenAICompatibleProvider:
    """Small JSON adapter with explicit model capabilities and execution metadata."""
    def __init__(self, *, provider_name, model_name, base_url, timeout_seconds=120.0,
                 max_tokens=8192, temperature=0.0, no_think=False, json_object=True,
                 auth_env=None, locality=None, model_id=None, route='analysis'):
        self.provider_name, self.model_name = provider_name, model_name
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds, self.max_tokens = timeout_seconds, max_tokens
        self.temperature, self.no_think, self.json_object = temperature, no_think, json_object
        self.auth_env, self.locality, self.model_id, self.route = auth_env, locality, model_id, route
        self._completion = local()
        self.last_completion = {}

    @property
    def last_completion(self):
        return getattr(self._completion, 'metadata', {})

    @last_completion.setter
    def last_completion(self, metadata):
        self._completion.metadata = metadata

    def complete_json(self, *, system, user, reasoning=False):
        from .model_registry import ModelConfig, guard_egress, RoutingError
        config = ModelConfig(provider=self.provider_name, model=self.model_name,
                             base_url=self.base_url, locality=self.locality)
        guard_egress(config)
        self.last_completion = {}
        headers = {'Content-Type': 'application/json'}
        if self.auth_env:
            secret = os.environ.get(self.auth_env)
            if not secret:
                raise RoutingError('missing_auth', 'Configured inference authentication is missing')
            headers['Authorization'] = f'Bearer {secret}'
        payload = {'model': self.model_name, 'messages': [
            {'role': 'system', 'content': ('/no_think\n\n' if self.no_think and not reasoning else '') + system},
            {'role': 'user', 'content': user}], 'temperature': self.temperature, 'max_tokens': self.max_tokens}
        if self.json_object:
            payload['response_format'] = {'type': 'json_object'}
        started = time.monotonic()
        try:
            with urlopen(Request(self.base_url + '/chat/completions', data=json.dumps(payload).encode(),
                                 headers=headers, method='POST'), timeout=self.timeout_seconds) as response:
                result = json.load(response)
        except Exception:
            raise RoutingError('completion_failed', 'Configured inference endpoint failed') from None
        try:
            choice = result['choices'][0]
            content, finish = choice['message']['content'], choice['finish_reason']
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError('Unexpected model response shape') from exc
        self.last_completion = {'chosen_model_id': self.model_id, 'route': self.route,
            'locality': config.locality, 'max_tokens': self.max_tokens, 'finish_reason': finish,
            'latency_ms': round((time.monotonic() - started) * 1000)}
        usage = result.get('usage') or {}
        for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
            if isinstance(usage.get(key), int) and not isinstance(usage[key], bool):
                self.last_completion[key] = usage[key]
        if finish != 'stop':
            raise ValueError(f'Model did not complete cleanly: finish_reason={finish}')
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError('Model response must be a JSON object')
        return parsed
