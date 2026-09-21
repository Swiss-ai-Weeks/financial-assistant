from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import historical_api
import investigation_api
import investigate_historical_pair as pipeline
from test_pair_simulation import make_signal
from financial_assistant.domain import SourceDocument
from financial_assistant.research.identity import resolve_entities


def test_scan_boundary_date_resolution_and_reconstruction(monkeypatch):
    prices = pd.DataFrame({'date': pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-05', '2026-01-06', '2026-01-09']),
                           'ticker': ['AAA'] * 5, 'close': [10, 11, 12, 13, 9999]})
    seen = []
    def scanner(frame, **kwargs):
        seen.append((frame.copy(), kwargs))
        assert frame.date.max().date() == kwargs['as_of']
        return ()
    monkeypatch.setattr(historical_api, 'scan_pairs_as_of', scanner)
    first = historical_api.historical_scan({'as_of': '2026-01-04'}, prices, 2)
    second = historical_api.historical_scan({'as_of': '2026-01-06'}, prices, 2)
    assert first['resolved_session'] == '2026-01-02'
    assert second['resolved_session'] == '2026-01-06'
    assert second['formation_end'] == '2026-01-05'
    assert first['fits_recomputed'] and second['fits_recomputed']
    assert len(seen[0][0]) == 2 and len(seen[1][0]) == 4
    assert 'fits' not in seen[0][1]  # No live-fit cache parameter or import.


def test_historical_engine_excludes_outcome_and_persists_replay(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    signal = make_signal()
    metadata = {'as_of': '2026-01-06', 'resolved_session': '2026-01-06'}
    monkeypatch.setattr(investigation_api, 'selected_signal', lambda request: (metadata, signal))
    graph = Mock(investigation_id='test')
    graph.model_copy.return_value.model_dump.return_value = {'nodes': [], 'edges': []}
    calls = []
    def engine(received, **kwargs):
        assert received is signal
        assert set(kwargs) == {'observed_at', 'provider', 'progress'}
        assert kwargs['observed_at'] == datetime(2026, 1, 6, 23, 59, 59, 999999, timezone.utc)
        calls.append('engine')
        return graph, object()
    def simulator(received, prices):
        assert calls == ['engine']
        calls.append('outcome')
        return SimpleNamespace(model_dump=lambda **kw: {'return_to_latest_pct': 99})
    monkeypatch.setattr(investigation_api, 'investigate_signal', engine)
    monkeypatch.setattr(investigation_api, 'simulate_pair_forward', simulator)
    monkeypatch.setattr(investigation_api, 'monitor_pairs', Mock(side_effect=AssertionError('Live fit reused')))
    result = investigation_api.investigate({'mode': 'historical', **investigation_api.public_models()['models'][0]},
        prices=object(), fits=object(), as_of=date(2099, 1, 1), formation_observations=252)
    assert result['nodes'] == [] and result['edges'] == []
    assert result['hindsight_outcome']['return_to_latest_pct'] == 99
    assert calls == ['engine', 'outcome']
    saved = json.loads(next((tmp_path / '.run/replays').glob('*.json')).read_text())
    assert saved == result


def test_scan_snapshot_rejects_forged_date_pair_and_missing_scan():
    historical_api._SCANS['test'] = ({'as_of': '2026-01-06'}, (make_signal(),))
    valid = {'scan_id':'test', 'as_of':'2026-01-06', 'ticker_a':'AAA', 'ticker_b':'BBB'}
    assert historical_api.selected_signal(valid)[1].fit.ticker_a == 'AAA'
    for patch in ({'as_of':'2026-01-07'}, {'ticker_a':'FORGED'}, {'scan_id':'missing'}):
        with pytest.raises(ValueError):
            historical_api.selected_signal({**valid, **patch})


def test_publication_cutoff_never_uses_retrieval_or_event_time():
    def doc(identifier, publication, date_only=False):
        return SourceDocument(document_id=identifier, title=identifier, publisher='FT',
            url=f'https://example.org/{identifier}', text='Actual source text',
            published_at=publication, published_date_only=date_only,
            retrieved_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
    docs = (doc('same', datetime(2026, 1, 6, tzinfo=timezone.utc), True),
            doc('future', datetime(2026, 1, 7, tzinfo=timezone.utc)), doc('undated', None))
    bundle = SimpleNamespace(documents=docs, records=(), query_expansions=())
    for hour, expected in ((12, []), (23, ['same'])):
        plan = SimpleNamespace(tasks=(), as_of=datetime(2026, 1, 6, hour, 59, 59, 999999, timezone.utc))
        selected = pipeline.select_historical_documents(bundle, plan, limit=10)
        assert [d.document_id for d in selected] == expected
        if selected:
            assert selected[0].published_date_only


def test_deterministic_issuer_aliases():
    assert resolve_entities(('BUSE', 'PNW')) == ('BUSE', 'FIRST BUSEY', 'PNW', 'PINNACLE WEST')


def test_real_fits_ignore_mutated_future_and_change_with_date():
    import numpy as np
    from financial_assistant.anomaly_detection.historical import scan_pairs_as_of
    rng = np.random.default_rng(0)
    dates = pd.bdate_range('2024-01-01', periods=290)
    common = 4 + np.cumsum(rng.normal(0, .012, len(dates)))
    noise = rng.normal(0, .002, len(dates))
    noise[270] = .07
    noise[271] = -.08
    prices = pd.DataFrame([{'date': day, 'ticker': ticker, 'close': np.exp(value)}
                          for i, day in enumerate(dates)
                          for ticker, value in [('AAA', common[i] + noise[i]), ('BBB', common[i])]])
    args = dict(formation_observations=252, corr_min=.5, alpha=.1, entry=1.5)
    first = scan_pairs_as_of(prices, as_of=dates[270].date(), **args)
    assert first
    changed = prices.copy()
    changed.loc[changed.date > dates[270], 'close'] *= 999
    assert scan_pairs_as_of(changed, as_of=dates[270].date(), **args) == first
    later = scan_pairs_as_of(prices, as_of=dates[271].date(), **args)
    assert later
    assert first[0].anomaly.z_score != later[0].anomaly.z_score
    assert first[0].fit.formation_end == dates[269].date()
    assert later[0].fit.formation_end == dates[270].date()


def test_precompute_and_historical_share_real_construction(tmp_path, monkeypatch):
    import precompute_demo_pairs
    from test_historical_scanner import international_prices
    from financial_assistant.anomaly_detection.models import PairFit
    from financial_assistant.anomaly_detection.cointegration import monitor_pairs
    prices, universe, day = international_prices()
    prices_path, universe_path, output = [tmp_path / name for name in ('prices.csv', 'universe.csv', 'fits.json')]
    prices.to_csv(prices_path, index=False)
    universe.to_csv(universe_path, index=False)
    monkeypatch.setattr(sys, 'argv', ['precompute_demo_pairs', '--prices', str(prices_path),
        '--universe', str(universe_path), '--output', str(output), '--as-of', str(day)])
    precompute_demo_pairs.main()
    payload = json.loads(output.read_text())
    construction = {k: payload[k] for k in ('formation_observations', 'corr_floor',
                                          'alpha_ceiling', 'max_peers_per_ticker')}
    from financial_assistant.anomaly_detection import historical
    reconstructed = []
    original_fitter = historical.fit_universe_pairs
    def capture_fits(*args, **kwargs):
        result = original_fitter(*args, **kwargs)
        reconstructed.extend(result[0])
        return result
    monkeypatch.setattr(historical, 'fit_universe_pairs', capture_fits)
    result = historical_api.historical_scan(dict(as_of=str(day), corr_min=.65, alpha=.05, entry=1.5),
                                            prices, universe=universe, **construction)
    fits = tuple(PairFit.model_validate({k: v for k, v in r.items() if k in PairFit.model_fields})
                 for r in payload['fits'])
    assert tuple(reconstructed) == fits
    eligible = tuple(f for f in fits if f.correlation >= .65 and f.pvalue < .05)
    _, anomalies = monitor_pairs(prices, eligible, start=day, end=day, entry=1.5)
    assert result['raw_fit_count'] == payload['fit_count'] > 0
    assert result['eligible_fit_count'] == len(eligible) > 0
    assert result['candidate_count'] == len(anomalies) > 0
    signals = historical_api._SCANS[result['scan_id']][1]
    by_pair = {(f.ticker_a, f.ticker_b): f for f in eligible}
    assert {(s.fit.ticker_a, s.fit.ticker_b) for s in signals} == {(a.ticker_a, a.ticker_b) for a in anomalies}
    assert all(s.fit == by_pair[s.fit.ticker_a, s.fit.ticker_b] for s in signals)
    assert all(result[k] == v for k, v in construction.items())
    assert result['price_securities'] == 4 and result['groups_processed'] == 1
    assert result['compute_backend'] == 'cpu' and result['elapsed_ms'] >= 0


def test_http_historical_route_passes_loaded_mapping_and_cache_policy(monkeypatch):
    import io
    import runpy
    cache = dict(fits=[], as_of='2026-09-18', formation_observations=200,
                 corr_floor=.55, alpha_ceiling=.08, max_peers_per_ticker=3)
    prices = pd.DataFrame(dict(date=['2026-09-18'], ticker=['AAA'], close=[100]))
    universe = pd.DataFrame(dict(yahoo_ticker=['AAA', 'BAD'], mapping_status=['mapped', 'unmapped']))
    reads = []
    def read_csv(path):
        reads.append(str(path))
        return universe.copy() if str(path).endswith('global_equities.csv') else prices.copy()
    monkeypatch.setattr(pd, 'read_csv', read_csv)
    from financial_assistant import universe as catalog_module
    mapped_rows = Mock(return_value=universe.to_dict('records'))
    monkeypatch.setattr(catalog_module, 'universe_rows', mapped_rows)
    monkeypatch.setattr(Path, 'exists', lambda *args: True)
    monkeypatch.setattr(Path, 'read_text', lambda *args, **kwargs: json.dumps(cache))
    scanner = Mock(return_value={'candidate_count': 0})
    monkeypatch.setattr(historical_api, 'historical_scan', scanner)
    server = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/anomaly_api.py'))
    handler = object.__new__(server['Handler'])
    handler.path = '/api/anomalies/historical-scan'
    handler.send_json = Mock()
    request = dict(as_of='2026-09-18', corr_min=.65, alpha=.05, entry=1.5)
    raw = json.dumps(request).encode()
    handler.headers = {'Content-Length': str(len(raw))}
    for _ in range(2):
        handler.rfile = io.BytesIO(raw)
        handler.do_POST()
    mapped_rows.assert_called_once_with()
    assert reads.count('data/cache/market/global_demo_daily.csv') == 1
    args, kwargs = scanner.call_args
    assert args[0] == request
    assert kwargs['universe'].yahoo_ticker.tolist() == ['AAA']
    assert {k: kwargs[k] for k in cache if k not in ('fits', 'as_of')} == {
        k: v for k, v in cache.items() if k not in ('fits', 'as_of')}
    assert 'fits' not in kwargs
    handler.send_json.assert_called_with(200, {'candidate_count': 0})
