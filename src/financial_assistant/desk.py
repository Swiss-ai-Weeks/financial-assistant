"""Read-only Pythia desk projections over ClaimGraph's canonical caches."""
from datetime import timedelta
import numpy as np
import pandas as pd
from financial_assistant.analytics.abnormal import HORIZONS, read_horizon, read_peers
from financial_assistant.portfolio.returns import price_series, security_returns, SOURCE
from financial_assistant.universe import LIMITATION


def cutoff_frame(prices, as_of):
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize('UTC')
    if len(str(as_of)) == 10:
        cutoff += timedelta(days=1) - timedelta(microseconds=1)
    dates = pd.to_datetime(prices.date, utc=True).dt.normalize()
    return prices.loc[dates + timedelta(days=1) - timedelta(microseconds=1) <= cutoff].copy()


def market_view(prices, ticker, as_of, days=180):
    if not 20 <= days <= 800:
        raise ValueError('days must be between 20 and 800')
    series = price_series(prices, ticker, as_of)
    tail = series.tail(days)
    return dict(ticker=ticker, as_of=as_of, last_session=str(series.index[-1].date()),
        candles=[dict(date=str(d.date()), close=float(v)) for d, v in tail.items()],
        metrics=security_returns(prices, ticker, as_of), source=SOURCE,
        membership_basis='current_snapshot', universe_limitation=LIMITATION)


def microscope(prices, ticker, as_of, benchmark='SPY'):
    frame = cutoff_frame(prices, as_of)
    ticks = []
    for horizon in HORIZONS:
        try:
            # Validate the input series; do not silently aggregate duplicate cache rows.
            for symbol in (ticker, benchmark):
                price_series(frame, symbol, as_of)
            reading = read_horizon(frame, ticker=ticker, benchmark=benchmark, horizon=horizon).model_dump()
            if not all(np.isfinite(v) for v in reading.values() if isinstance(v, float)):
                raise ValueError('Incomplete market or volume history')
            ticks.append(dict(status='available', **reading))
        except (KeyError, ValueError, IndexError):
            ticks.append(dict(horizon=horizon, status='unavailable',
                reason=f'Insufficient aligned price/volume history for {ticker} and {benchmark}'))
    peers = {}
    for horizon in HORIZONS:
        try:
            peers[horizon] = [p.model_dump() for p in read_peers(frame, ticker=ticker, benchmark=benchmark, horizon=horizon)]
        except (KeyError, ValueError, IndexError):
            peers[horizon] = []
    return dict(ticker=ticker, peers=peers, benchmark=benchmark, as_of=as_of, ticks=ticks,
        source=SOURCE, role='market_context', formula_version='pythia-market-model-v1',
        methodology='Lagged 252-session beta; abnormal daily volatility estimated before the measured horizon. Descriptive, not a forecast.',
        universe_limitation=LIMITATION)


def signal_context(prices, ticker, as_of):
    from financial_assistant.anomaly_detection.signals import detect_signal_anomalies
    frame = cutoff_frame(prices, as_of)
    frame = frame.loc[frame.ticker == ticker].copy()
    if frame.empty:
        return dict(status='unavailable', reason='No history for this security at cutoff', signals=[])
    if not {'date','ticker','open','high','low','close','volume'} <= set(frame.columns):
        return dict(status='unavailable', reason='OHLCV cache required for VWAP / TWAP / trend monitors', signals=[])
    date = pd.Timestamp(as_of).date()
    signals = detect_signal_anomalies(frame, ticker=ticker, start=date-timedelta(days=30), end=date)
    return dict(status='available', role='attention_events', as_of=as_of,
                signals=[s.model_dump(mode='json') for s in signals])
