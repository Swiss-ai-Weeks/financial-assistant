"""Deterministic ticker aliases; never ask a model to reinterpret a known ticker."""
import csv
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def issuer_names():
    path = Path(__file__).resolve().parents[3] / 'data/universe/global_equities.csv'
    names = {}
    if path.exists():
        with path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                if row['mapping_status'] == 'mapped':
                    names.setdefault(row['yahoo_ticker'], set()).add(row['name'])
    return {ticker: next(iter(values)) for ticker, values in names.items() if len(values) == 1}


def resolve_entities(entities):
    names = issuer_names()
    return tuple(dict.fromkeys(alias for entity in entities
                              for alias in (entity, names.get(entity, entity))))
