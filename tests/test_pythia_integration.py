"""Pythia adapters preserve canonical identity and temporal boundaries."""
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from financial_assistant.universe import catalog, merge_securities, universe_rows
from financial_assistant.desk import market_view, microscope
from financial_assistant.retrieval.archive import ArchiveSearchProvider, archive_items


def test_union_identity_and_multiple_current_memberships():
    rows = [dict(ticker='AAA', name='Alpha', exchange='NYSE', universe='sp500', source='a'),
            dict(yahoo_ticker='AAA', sector='Tech', universe='nasdaq100', source='b'),
            dict(ticker='AAA', universe='nasdaq100', source='b'), dict(ticker='BBB', universe='other')]
    result = merge_securities(rows)
    assert len(result) == 2
    assert result[0]['universes'] == ['sp500','nasdaq100']
    assert result[0]['name'] == 'Alpha' and result[0]['sector'] == 'Tech'
    assert result[0]['identity'] == 'AAA'
    assert len(result[0]['memberships']) == 2
    assert all(m['temporal_basis'] == 'current_snapshot' and m['effective_date'] is None for m in result[0]['memberships'])
    assert len(result[0]['sources']) == 3


def test_real_catalog_union_and_no_invented_identity():
    import csv
    root = Path(__file__).resolve().parents[1]
    with (root/'data/universe/global_equities.csv').open() as f:
        expected = {r['yahoo_ticker'] for r in csv.DictReader(f) if r['mapping_status']=='mapped'}
    securities = catalog()
    tickers = {s['ticker'] for s in securities}
    assert expected <= tickers
    assert {'NVDA','COHU','BAC','GLD','GDX'} <= tickers
    assert len(tickers) == len(securities)
    assert all(s['identity']==s['ticker'] for s in securities)
    assert all('valid_from' not in r for r in universe_rows())
    assert merge_securities([dict(raw_ticker='unresolved',mapping_status='unmapped')]) == []


def market():
    rng = np.random.default_rng(9)
    dates = pd.bdate_range('2022-01-01',periods=820)
    base=rng.normal(.0002,.008,len(dates))
    return pd.concat([pd.DataFrame(dict(date=dates,ticker=t,close=100*np.exp(np.cumsum(base+rng.normal(0,noise,len(dates)))),volume=1000000.)) for t,noise in [('SPY',.001),('AAA',.006)]],ignore_index=True)


def test_market_and_microscope_cut_before_computing():
    prices=market(); cutoff=str(prices.date.unique()[-30])[:10]
    past=prices[prices.date<=cutoff].copy()
    changed=prices.copy(); changed.loc[changed.date>cutoff,'close'] *= 100
    assert market_view(prices,'AAA',cutoff) == market_view(past,'AAA',cutoff) == market_view(changed,'AAA',cutoff)
    assert microscope(prices,'AAA',cutoff) == microscope(past,'AAA',cutoff) == microscope(changed,'AAA',cutoff)
    assert all(t['status']=='available' for t in microscope(prices,'AAA',cutoff)['ticks'])
    result=market_view(prices,'AAA',cutoff+'T12:00:00Z')
    assert result['last_session'] < cutoff
    assert 'Current constituent' in result['universe_limitation']


def test_missing_market_and_benchmark_are_not_fabricated():
    with pytest.raises(ValueError): market_view(market(),'MISSING','2026-01-01')
    result=microscope(market().query("ticker == 'AAA'"),'AAA','2026-01-01')
    assert all(t['status']=='unavailable' for t in result['ticks'])


def test_archive_is_candidate_not_evidence_and_respects_cutoff(tmp_path):
    def row(id, date, **extra):
        return dict(news_id=id,ticker='AAA',title='Alpha earnings report',summary='Revenue',published_at=date,url='https://example.com/'+id,source='archive',**extra)
    rows=[row('old','2025-01-01T10:00:00Z'),row('later','2025-01-02T10:00:00Z'),
          row('date','2025-01-01'),row('unknown','bad')]
    (tmp_path/'AAA.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    cutoff=datetime(2025,1,1,12,tzinfo=timezone.utc)
    items=archive_items(tmp_path,ticker='AAA',as_of=cutoff)
    assert [i['news_id'] for i in items] == ['old']
    assert items[0]['role']=='retrieval_candidate'
    hits=ArchiveSearchProvider(tmp_path).search('Alpha',task_id='T',as_of=cutoff)
    assert len(hits)==1 and hits[0].provider=='pythia_archive' and hits[0].hit_id=='archive:old'
    assert hits[0].published_at <= cutoff
    with pytest.raises(ValueError): archive_items(tmp_path,ticker='../secret')


def test_bookreader_and_archive_both_wired_to_initial_and_followup():
    root=Path(__file__).resolve().parents[1]
    for name in ['investigate_historical_pair.py','missing_evidence_followup.py']:
        source=(root/'scripts'/name).read_text()
        assert 'CorpusSearchProvider' in source and 'CorpusDocumentFetcher' in source
        assert 'ArchiveSearchProvider()' in source
        assert '"pythia_archive"' in source or "'pythia_archive'" in source
        assert 'DispatchingDocumentFetcher' in source


def test_prospective_security_uses_existing_engine_without_becoming_holding(monkeypatch):
    import sys
    import importlib
    from unittest.mock import Mock
    from datetime import date
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    api=importlib.import_module('investigation_api')
    graph=Mock(investigation_id='prospect')
    graph.model_copy.return_value.model_dump.return_value={'nodes':[],'edges':[]}
    engine=Mock(return_value=(graph,None))
    monkeypatch.setattr(api,'investigate_signal',engine)
    request={'mode':'security','ticker_a':'NVDA','as_of':'2024-06-28',
        'portfolio':{'positions':[{'ticker':'AAA','weight':1}]},**api.public_models()['models'][0]}
    result=api.investigate(request,prices=market(),fits=[],as_of=date(2026,1,1),formation_observations=252)
    event=engine.call_args.kwargs['event_override']
    assert event.ticker=='NVDA' and 'portfolio_weight' not in event.metadata
    assert event.anomaly_type=='human_research_request'
    assert 'portfolio holding' not in event.summary
    assert not any(e['kind']=='supports' for e in result['edges'])


def test_single_security_monitors_are_cutoff_safe():
    from financial_assistant.desk import signal_context
    frame=market()
    for column in ('open','high','low'): frame[column]=frame.close
    frame.loc[(frame.ticker=='AAA') & (frame.date==frame.date.max()),'close'] *= 1.3
    cutoff=str(frame.date.unique()[-10])[:10]
    assert signal_context(frame,'AAA',cutoff)==signal_context(frame[frame.date<=cutoff],'AAA',cutoff)
    assert signal_context(frame,'AAA',cutoff)['status']=='available'
    assert signal_context(frame,'missing',cutoff)['status']=='unavailable'


def test_readonly_desk_http_routes_and_missing_cache(monkeypatch):
    import runpy
    import sys
    from unittest.mock import Mock
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    # No sockets or provider calls: execute the actual handler directly.
    server=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/anomaly_api.py'))
    handler=object.__new__(server['Handler'])
    handler.send_json=Mock()
    handler.do_GET.__func__.__globals__['PRICES']=market()
    for path in ['/api/instruments/search?q=NVDA', '/api/market/AAA/candles?as_of=2024-01-01',
                 '/api/microscope/AAA?as_of=2024-01-01', '/api/market/tape?tickers=AAA,SPY&as_of=2024-01-01',
                 '/api/news?ticker=AAA&as_of=2024-01-01', '/api/market/AAA/signals?as_of=2024-01-01']:
        handler.path=path
        handler.do_GET()
        assert handler.send_json.call_args.args[0]==200, path
    handler.path='/api/market/AAA/candles?as_of=not-a-date'
    handler.do_GET()
    assert handler.send_json.call_args.args[0]==400
