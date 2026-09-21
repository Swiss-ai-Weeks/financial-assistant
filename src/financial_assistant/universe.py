"""One catalog; source memberships are current snapshots, never historical facts."""
import json
from functools import lru_cache
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / 'data/universe/securities.json'
LIMITATION = 'Current constituent snapshots only; historical membership, survivorship and data revisions are not reconstructed.'


def merge_securities(rows):
    securities = {}
    for original in rows:
        row = {k: v for k, v in original.items() if v is not None and v != ''}
        ticker = str(row.get('yahoo_ticker') or row.get('ticker') or '').strip().upper()
        if not ticker or row.get('mapping_status', 'mapped') != 'mapped':
            continue
        security = securities.setdefault(ticker, dict(identity=ticker, identity_scheme='yahoo_ticker',
            ticker=ticker, name=ticker, exchange=None, universes=[], memberships=[], sources=[]))
        for key in ('name', 'exchange', 'sector', 'currency', 'location'):
            if row.get(key) and (not security.get(key) or security.get(key) == ticker):
                security[key] = row[key]
        universe = row.get('universe', 'unspecified')
        if universe not in security['universes']:
            security['universes'].append(universe)
        membership = dict(universe=universe, source=row.get('source', 'unknown'),
                          temporal_basis='current_snapshot', effective_date=None)
        if membership not in security['memberships']:
            security['memberships'].append(membership)
        if row not in security['sources']:
            security['sources'].append(row)
    return [securities[t] for t in sorted(securities)]


@lru_cache(maxsize=1)
def catalog():
    return json.loads(CATALOG.read_text())['securities']


def universe_rows(securities=None):
    """Membership projection for existing fitters, not duplicate security records."""
    return [dict(yahoo_ticker=s['ticker'], name=s['name'], sector=s.get('sector', ''),
                 currency=s.get('currency', ''), exchange=s.get('exchange', ''),
                 universe=u, mapping_status='mapped', membership_basis='current_snapshot')
            for s in (catalog() if securities is None else securities) for u in s['universes']]


def search(query, limit=30):
    query = query.strip().casefold()
    matches = [s for s in catalog() if query in s['ticker'].casefold() or query in s['name'].casefold()]
    return sorted(matches, key=lambda s: (s['ticker'].casefold() != query, not s['ticker'].casefold().startswith(query), s['ticker']))[:limit]
