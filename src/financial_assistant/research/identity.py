"""Deterministic ticker aliases; never ask a model to reinterpret a known ticker."""
from functools import lru_cache


@lru_cache(maxsize=1)
def issuer_names():
    from financial_assistant.universe import catalog
    return {s['ticker']: s['name'] for s in catalog() if s['name'] != s['ticker']}


def resolve_entities(entities):
    names = issuer_names()
    return tuple(dict.fromkeys(alias for entity in entities
                              for alias in (entity, names.get(entity, entity))))
