"""Point-in-time scans. Never imports or consults the live pair-fit cache."""
from collections import OrderedDict
from datetime import date, timedelta
from threading import Lock
from time import perf_counter
from uuid import uuid4

import pandas as pd
from financial_assistant.anomaly_detection.historical import scan_pairs_as_of

_SCANS = OrderedDict()
_LOCK = Lock()


def historical_scan(request, prices, formation_observations=252, *, universe=None,
                    corr_floor=.50, alpha_ceiling=.10, max_peers_per_ticker=5):
    requested = date.fromisoformat(request['as_of'])
    corr, alpha, entry = (float(request.get(k, v)) for k, v in
                          [('corr_min', .65), ('alpha', .05), ('entry', 1.5)])
    if not (corr_floor <= corr <= 1 and .0001 <= alpha <= alpha_ceiling and .5 <= entry <= 4):
        raise ValueError('Invalid historical scan thresholds')
    started = perf_counter()
    # Cut before pair selection, including eligibility checks.
    available = prices.loc[pd.to_datetime(prices.date).dt.date <= requested].copy()
    if available.empty:
        raise ValueError('No market session on or before selected date')
    session = pd.Timestamp(available.date.max()).date()
    diagnostics = {}
    signals = scan_pairs_as_of(available, as_of=session,
                              formation_observations=formation_observations,
                              corr_min=corr, alpha=alpha, entry=entry,
                              universe=universe, corr_floor=corr_floor,
                              alpha_ceiling=alpha_ceiling,
                              max_peers_per_ticker=max_peers_per_ticker,
                              diagnostics=diagnostics)
    scan_id = str(uuid4())
    # This is the screening envelope; candidate PairFits carry exact windows.
    formation_start = session - timedelta(days=450)
    formation_end = session - timedelta(days=1)
    metadata = dict(as_of=requested.isoformat(), resolved_session=session.isoformat(),
                    formation_start=formation_start.isoformat(), formation_end=formation_end.isoformat(),
                    price_observations_through=session.isoformat(), fits_recomputed=True,
                    operation='historical_market_reconstruction', **diagnostics,
                    universe_limitation='Available cache universe; survivorship and historical data revisions are not reconstructed.',
                    elapsed_ms=round((perf_counter()-started)*1000, 1))
    with _LOCK:
        _SCANS[scan_id] = (metadata, signals)
        while len(_SCANS) > 16:
            _SCANS.popitem(last=False)
    candidates = []
    for signal in signals[:50]:
        fit, anomaly = signal.fit, signal.anomaly
        candidates.append(dict(mode='historical', scan_id=scan_id, requested_as_of=requested.isoformat(),
            pair=f'{fit.ticker_a}/{fit.ticker_b}', ticker_a=fit.ticker_a, ticker_b=fit.ticker_b,
            signal_date=session.isoformat(), z_score=anomaly.z_score, threshold=entry,
            correlation=fit.correlation, cointegration_p=fit.pvalue, beta=fit.beta,
            formation_start=fit.formation_start.isoformat(), formation_end=fit.formation_end.isoformat()))
    return dict(**metadata, scan_id=scan_id, candidates=candidates, candidate_count=len(signals),
                cache=dict(price_securities=int(available.ticker.nunique())))


def selected_signal(request):
    with _LOCK:
        snapshot = _SCANS.get(request.get('scan_id'))
    if snapshot is None:
        raise ValueError('Historical scan expired; Travel again')
    metadata, signals = snapshot
    if request.get('as_of') != metadata['as_of']:
        raise ValueError('Selected date differs from historical scan')
    signal = next((s for s in signals if (s.fit.ticker_a, s.fit.ticker_b) ==
                   (request.get('ticker_a'), request.get('ticker_b'))), None)
    if signal is None:
        raise ValueError('Pair is not an anomaly in this historical scan')
    return metadata.copy(), signal
