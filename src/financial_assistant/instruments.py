"""Searchable securities are independent of membership and cached analytics."""
from functools import lru_cache
import yfinance as yf
from .universe import catalog, LIMITATION


@lru_cache(maxsize=256)
def yahoo_search(query, limit):
    return tuple(yf.Search(query, max_results=limit * 2, news_count=0).quotes)


def resolve(query, *, limit=30, searcher=None, market_tickers=None, fit_tickers=None):
    text = query.strip()
    if not text:
        return dict(securities=[], yahoo_status='not_requested', limitation=LIMITATION)
    canonical = {s['ticker'].upper(): s for s in catalog()}
    matches = {t: dict(s) for t, s in canonical.items()
               if text.casefold() in t.casefold() or text.casefold() in s['name'].casefold()}
    status = 'available'
    try:
        quotes = (searcher or yahoo_search)(text, limit)
        for quote in quotes:
            ticker = str(quote.get('symbol') or '').strip().upper()
            if not ticker or quote.get('quoteType') not in {'EQUITY', 'ETF'}:
                continue
            matches.setdefault(ticker, dict(canonical.get(ticker) or dict(
                identity=ticker, identity_scheme='yahoo_ticker', ticker=ticker,
                name=quote.get('longname') or quote.get('shortname') or ticker,
                exchange=quote.get('exchDisp'), sector=quote.get('sectorDisp'),
                kind=quote.get('quoteType'), universes=[], memberships=[], sources=[])))
    except Exception:
        status = 'unavailable'
    results = []
    for ticker, security in matches.items():
        security.update(catalogued=ticker in canonical, dynamically_resolved=ticker not in canonical,
                        resolution_source='catalog' if ticker in canonical else 'yahoo-finance',
                        coverage=dict(market_cache=None if market_tickers is None else ticker in market_tickers,
                                      precomputed_pairs=None if fit_tickers is None else ticker in fit_tickers))
        results.append(security)
    results.sort(key=lambda s: (s['ticker'].casefold() != text.casefold(),
                               not s['ticker'].casefold().startswith(text.casefold()), s['ticker']))
    return dict(securities=results[:limit], yahoo_status=status, limitation=LIMITATION)


def company_name(ticker):
    local = next((s['name'] for s in catalog() if s['ticker'] == ticker), None)
    if local:
        return local
    return next((s['name'] for s in resolve(ticker)['securities'] if s['ticker'] == ticker), ticker)
