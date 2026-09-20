"""Versioned close-to-close calculations. All outputs are decimal ratios."""
from datetime import timedelta
import hashlib
import json
import numpy as np
import pandas as pd

VERSION = 'market-performance-v1'
SOURCE = 'data/cache/market/global_demo_daily.csv'


def unavailable(reason):
    return {'status': 'unavailable', 'reason': reason, 'value': None}


def metric(value, formula, **metadata):
    if not np.isfinite(value):
        return unavailable('Non-finite calculation')
    return dict(status='available', value=float(value), unit='ratio', formula=formula,
                formula_version=VERSION, **metadata)


def validate_portfolio(portfolio):
    positions = portfolio.get('positions', [])
    if not positions or len(positions) > 100:
        raise ValueError('Supply 1–100 positions')
    tickers = [p['ticker'].strip().upper() for p in positions]
    weights = np.array([float(p['weight']) for p in positions])
    if any(not t for t in tickers) or len(set(tickers)) != len(tickers):
        raise ValueError('Tickers must be nonempty and unique')
    if not np.isfinite(weights).all() or (weights < 0).any() or abs(weights.sum()-1) > .001:
        raise ValueError('Nonnegative finite weights must sum to 1 (tolerance 0.001)')
    # Explicit normalization within tolerance, retained in provenance.
    return dict(zip(tickers, weights / weights.sum()))


def price_series(prices, ticker, as_of):
    if not isinstance(prices, pd.DataFrame) or not {'date', 'ticker', 'close'} <= set(prices.columns):
        raise ValueError('Historical close-price cache unavailable')
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize('UTC') if cutoff.tzinfo is None else cutoff.tz_convert('UTC')
    # Daily bars are available only after the whole UTC session date elapsed.
    if len(str(as_of)) == 10:
        cutoff += timedelta(days=1) - timedelta(microseconds=1)
    dates = pd.to_datetime(prices['date'], utc=True).dt.normalize()
    selected = prices.loc[(prices.ticker == ticker) & (dates + timedelta(days=1) - timedelta(microseconds=1) <= cutoff)].copy()
    selected['date'] = dates.loc[selected.index]
    if selected.empty:
        raise ValueError(f'Missing security/history at cutoff: {ticker}')
    if selected.date.duplicated().any():
        raise ValueError(f'Ambiguous duplicate price dates: {ticker}')
    series = selected.set_index('date')['close'].sort_index().astype(float)
    if not np.isfinite(series).all() or (series <= 0).any():
        raise ValueError(f'Invalid close prices: {ticker}')
    return series.rename(ticker)


def daily_returns(series):
    returns = series.pct_change(fill_method=None)
    # Never bridge long gaps; annualization would otherwise treat multiweek returns as daily.
    return returns.where(series.index.to_series().diff() <= timedelta(days=4)).dropna()


def realized_volatility(returns):
    if len(returns) < 2:
        return unavailable('Insufficient return history for volatility')
    return metric(returns.std(ddof=1) * np.sqrt(252), 'sample_std(daily_returns, ddof=1) * sqrt(252)')


def max_drawdown(returns):
    if len(returns) == 0:
        return unavailable('Insufficient return history for drawdown')
    wealth = np.r_[1., np.cumprod(1 + np.asarray(returns))]
    return metric(np.min(wealth / np.maximum.accumulate(wealth) - 1), 'min(wealth / running_max(wealth) - 1), initial wealth=1')


def observation(ticker, date, value):
    return dict(kind='observation', ticker=ticker, date=str(date.date()), price_field='close',
                value=float(value), source=SOURCE)


def security_returns(prices, ticker, as_of):
    try:
        series = price_series(prices, ticker, as_of)
    except ValueError as exc:
        return unavailable(str(exc))
    gaps = np.flatnonzero(series.index.to_series().diff() > timedelta(days=4))
    if len(gaps):
        series = series.iloc[gaps[-1]:]
    returns = daily_returns(series)
    result = dict(status='available', ticker=ticker, as_of=str(as_of), last_session=str(series.index[-1].date()))
    for n in (1, 5, 20, 63, 252):
        if len(series) <= n or series.tail(n+1).index.to_series().diff().max() > timedelta(days=4):
            result[f'return_{n}'] = unavailable(f'Insufficient contiguous history: {n} sessions')
        else:
            result[f'return_{n}'] = metric(series.iloc[-1]/series.iloc[-n-1]-1, 'end_close / start_close - 1',
                ticker=ticker, as_of_cutoff=str(as_of), inputs=[observation(ticker, series.index[i], series.iloc[i]) for i in (-n-1, -1)])
    for n in (20, 60):
        recent = returns.reindex(series.index[-n:]).dropna()
        result[f'volatility_{n}'] = realized_volatility(recent) if len(recent) == n else unavailable(f'Insufficient history: {n} daily returns')
    result['max_drawdown'] = max_drawdown(returns.tail(252))
    return result


def aligned_returns(prices, tickers, as_of):
    series = [price_series(prices, t, as_of) for t in dict.fromkeys(tickers)]
    # Align return intervals, not just ending dates. Missing sessions never become invented daily bars.
    frames = []
    for s in series:
        frame = daily_returns(s).to_frame()
        frame['start'] = s.index.to_series().shift().reindex(frame.index)
        frames.append(frame)
    merged = frames[0]
    for i, frame in enumerate(frames[1:]):
        merged = merged.join(frame.rename(columns={'start': f'start_{i}'}), how='inner')
        merged = merged.loc[merged.start == merged[f'start_{i}']].drop(columns=f'start_{i}')
    merged = merged.drop(columns='start')
    if len(merged) < 2:
        raise ValueError('Insufficient overlap / incompatible price calendars')
    # Keep the most recent contiguous common interval; do not compress holes into daily time.
    union = series[0].index
    for s in series[1:]:
        union = union.union(s.index)
    if merged.index[-1] != union[-1]:
        raise ValueError('Incompatible price calendars: latest common return unavailable')
    locations = union.get_indexer(merged.index)
    breaks = np.flatnonzero(np.diff(locations) != 1)
    if len(breaks):
        merged = merged.iloc[breaks[-1]+1:]
    if len(merged) < 2:
        raise ValueError('Insufficient contiguous common sessions')
    return merged


def portfolio_return_series(returns, weights):
    return returns[list(weights)].mul(pd.Series(weights)).sum(axis=1)


def holding_contributions(returns, weights):
    portfolio = portfolio_return_series(returns, weights)
    prior_wealth = (1+portfolio).cumprod().shift(fill_value=1)
    return returns[list(weights)].mul(pd.Series(weights)).mul(prior_wealth, axis=0).sum().to_dict()


def pair_return_series(returns, ticker_a, ticker_b):
    if ticker_a == ticker_b:
        raise ValueError('Candidate not simulatable: two different tickers required')
    return .5 * (returns[ticker_a] - returns[ticker_b])


def summary(returns):
    return dict(return_window=metric((1+returns).prod()-1, 'product(1 + daily_return) - 1'),
                volatility=realized_volatility(returns), max_drawdown=max_drawdown(returns), sessions=len(returns),
                start=str(returns.index[0].date()), end=str(returns.index[-1].date()))


def provenance(prices, tickers, as_of):
    inputs = {t: [observation(t, d, v) for d, v in price_series(prices, t, as_of).items()] for t in dict.fromkeys(tickers)}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return dict(formula_version=VERSION, as_of_cutoff=str(as_of), source=SOURCE, price_field='close',
                inputs=inputs, input_sha256=digest, annualization=252,
                assumptions=['Cached adjusted close; historical revisions are not reconstructed',
                             'Exact shared return intervals; no forward filling', 'Fixed daily weights; no costs or financing'])


def analyze_portfolio(prices, portfolio, as_of):
    try:
        weights = validate_portfolio(portfolio)
        securities = {t: security_returns(prices, t, as_of) for t in weights}
        aligned = aligned_returns(prices, weights, as_of)
        returns = portfolio_return_series(aligned, weights)
        result = dict(status='available', portfolio=portfolio, weights=weights, as_of=str(as_of), securities=securities,
                      summary=summary(returns.tail(252)), concentration=dict(largest_weight=max(weights.values()), hhi=sum(w*w for w in weights.values())),
                      provenance=provenance(prices, weights, as_of))
        for n in (1, 5, 20, 63):
            result[f'return_{n}'] = metric((1+returns.tail(n)).prod()-1, 'product(1 + sum(weight * daily_return)) - 1') if len(returns) >= n else unavailable(f'Insufficient common history: {n} sessions')
        result['contributions_20'] = holding_contributions(aligned.tail(20), weights) if len(aligned) >= 20 else unavailable('Insufficient history: 20 common sessions')
        return result
    except (ValueError, KeyError, TypeError) as exc:
        return unavailable(str(exc))


def simulate_overlay(prices, portfolio, candidate, as_of, gross=.02, lookback=252):
    try:
        weights = validate_portfolio(portfolio)
        gross, lookback = float(gross), int(lookback)
        if not np.isfinite(gross) or not 0 <= gross <= 1 or not 20 <= lookback <= 252:
            raise ValueError('Gross overlay must be 0–1; lookback 20–252 sessions')
        a, b = candidate['ticker_a'], candidate['ticker_b']
        aligned = aligned_returns(prices, [*weights, a, b], as_of).tail(lookback)
        if len(aligned) < 20:
            raise ValueError('Insufficient overlap: at least 20 common sessions required')
        base = portfolio_return_series(aligned, weights)
        pair = pair_return_series(aligned, a, b)
        correlation = metric(base.corr(pair), 'Pearson correlation of aligned daily returns') if base.std() > 0 and pair.std() > 0 else unavailable('Correlation undefined for constant returns')
        return dict(status='available', kind='calculation', as_of=str(as_of), portfolio=portfolio, weights=weights,
                    candidate=candidate, gross_overlay=gross, requested_sessions=lookback,
                    construction='Analytical A-relative-to-B scenario: 0.5*rA - 0.5*rB; no inferred trade direction',
                    formula='combined_daily = portfolio_daily + gross_overlay * (0.5*rA - 0.5*rB)',
                    formula_version=VERSION, current=summary(base), candidate_performance=summary(pair), combined=summary(base+gross*pair),
                    correlation=correlation, securities={t: security_returns(prices,t,as_of) for t in (a,b)},
                    provenance=provenance(prices, [*weights,a,b], as_of),
                    remaining_question='Is the economic relationship sufficiently stable for the historical diversification pattern to remain plausible?',
                    interpretation='Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.')
    except (ValueError, KeyError, TypeError) as exc:
        return unavailable(str(exc))
