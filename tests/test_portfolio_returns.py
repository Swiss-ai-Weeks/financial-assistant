from copy import deepcopy
from datetime import timedelta
import importlib
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from financial_assistant.portfolio.returns import (
    VERSION, security_returns, realized_volatility, max_drawdown, aligned_returns,
    portfolio_return_series, holding_contributions, simulate_overlay, analyze_portfolio,
    validate_portfolio, price_series,
)
from financial_assistant.portfolio.service import market_context, attach_market_graph


def prices(n=300):
    dates = pd.bdate_range('2024-01-01', periods=n)
    x = np.arange(n)
    return pd.DataFrame([{'date':d,'ticker':t,'close':v} for t,values in
        [('AAA',100*np.exp(.001*x+.02*np.sin(x))),('BBB',100*np.exp(.0003*x+.01*np.cos(x)))]
        for d,v in zip(dates,values)])


P = {'id':'fixture','name':'Fictional weights', 'positions':[{'ticker':'AAA','weight':.6},{'ticker':'BBB','weight':.4}]}


@pytest.mark.parametrize('n',[1,5,20,63,252])
def test_security_returns(n):
    frame = prices()
    series = frame[frame.ticker == 'AAA'].close
    result = security_returns(frame,'AAA','2026-01-01')[f'return_{n}']
    assert result['value'] == pytest.approx(series.iloc[-1]/series.iloc[-n-1]-1)
    assert result['formula_version'] == VERSION
    assert len(result['inputs']) == 2
    assert result == security_returns(frame,'AAA','2026-01-01')[f'return_{n}']


def test_volatility_drawdown():
    returns = pd.Series([.1,-.2,.1])
    assert realized_volatility(returns)['value'] == pytest.approx(np.std(returns,ddof=1)*np.sqrt(252))
    assert max_drawdown(returns)['value'] == pytest.approx(-.2)
    assert max_drawdown(pd.Series([-.2,.1]))['value'] == pytest.approx(-.2)
    assert realized_volatility(pd.Series([1]))['status'] == 'unavailable'


def test_portfolio_and_contributions():
    returns = aligned_returns(prices(),['AAA','BBB'],'2026-01-01').tail(20)
    weights = validate_portfolio(P)
    portfolio = portfolio_return_series(returns,weights)
    assert np.allclose(portfolio,.6*returns.AAA+.4*returns.BBB)
    contribution = holding_contributions(returns,weights)
    assert sum(contribution.values()) == pytest.approx((1+portfolio).prod()-1)
    result = analyze_portfolio(prices(),P,'2026-01-01')
    assert result['status'] == 'available'
    assert result['return_20']['value'] == pytest.approx(sum(contribution.values()))


def test_alignment_and_gaps():
    frame = prices(100)
    missing = frame[(frame.ticker == 'BBB')].iloc[50].date
    frame = frame[~((frame.ticker == 'BBB') & (frame.date == missing))]
    aligned = aligned_returns(frame,['AAA','BBB'],'2026-01-01')
    assert (aligned.index > pd.Timestamp(missing,tz='UTC')).all()
    # The day after a missing price also cannot align its starting observation.
    assert len(aligned) == 48
    short = frame[frame.date <= missing+timedelta(days=1)]
    with pytest.raises(ValueError):
        aligned_returns(short,['AAA','BBB'],'2026-01-01')


def test_unavailable_inputs():
    assert security_returns(prices(5),'AAA','2026-01-01')['return_5']['status'] == 'unavailable'
    assert security_returns(prices(),'MISSING','2026-01-01')['status'] == 'unavailable'
    assert simulate_overlay(prices(10),P,{'ticker_a':'AAA','ticker_b':'BBB'},'2026-01-01')['status'] == 'unavailable'
    assert simulate_overlay(prices(),P,{'ticker_a':'AAA'},'2026-01-01')['status'] == 'unavailable'
    assert simulate_overlay(prices(),P,{'ticker_a':'AAA','ticker_b':'AAA'},'2026-01-01')['status'] == 'unavailable'
    for value in (-1, float('nan'), .8):
        bad = deepcopy(P); bad['positions'][0]['weight'] = value
        assert analyze_portfolio(prices(),bad,'2026-01-01')['status'] == 'unavailable'


def test_overlay_correlation_and_provenance():
    frame=prices(); candidate={'ticker_a':'AAA','ticker_b':'BBB'}
    result = simulate_overlay(frame,P,candidate,'2026-01-01')
    aligned = aligned_returns(frame,['AAA','BBB'],'2026-01-01').tail(252)
    base=.6*aligned.AAA+.4*aligned.BBB; pair=.5*(aligned.AAA-aligned.BBB)
    assert result['correlation']['value'] == pytest.approx(base.corr(pair))
    assert result['combined']['return_window']['value'] == pytest.approx((1+base+.02*pair).prod()-1)
    assert result['formula_version'] == VERSION
    assert 'no inferred trade direction' in result['construction']
    assert result == simulate_overlay(frame,P,candidate,'2026-01-01')


def test_no_lookahead_or_future_hash_changes():
    frame=prices(); cutoff='2024-06-28'; candidate={'ticker_a':'AAA','ticker_b':'BBB'}
    changed=frame.copy(); changed.loc[changed.date > cutoff,'close'] *= 100
    assert security_returns(frame,'AAA',cutoff) == security_returns(changed,'AAA',cutoff)
    assert analyze_portfolio(frame,P,cutoff) == analyze_portfolio(changed,P,cutoff)
    assert simulate_overlay(frame,P,candidate,cutoff) == simulate_overlay(changed,P,candidate,cutoff)
    assert price_series(frame,'AAA','2024-06-28T12:00:00Z').index[-1].day == 27
    assert price_series(frame,'AAA','2024-06-28T23:59:59.999999Z').index[-1].day == 28


def test_context_and_graph_are_descriptive():
    context=market_context(['AAA','BBB'],'2024-06-28',prices())
    graph=attach_market_graph({'nodes':[],'edges':[]},context)
    assert {n['kind'] for n in graph['nodes']} == {'observation','calculation'}
    assert {e['kind'] for e in graph['edges']} == {'calculated_from'}
    assert 'not causal evidence' in context['interpretation']
    assert len(graph['nodes']) <= 18


def test_followup_delta_and_history():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    followup_delta=importlib.import_module('missing_evidence_followup').followup_delta
    before={'nodes':[{'node_id':'M','kind':'missing_evidence','data':{}},{'node_id':'H','kind':'hypothesis','data':{}}], 'edges':[], 'followups':[{'run_id':'old'}]}
    after=deepcopy(before)
    after['nodes'][0]['data']={'resolution_status':'partially_answered','resolution':{'remaining_question':'Why?'}}
    after['nodes'].append({'node_id':'C','kind':'claim','data':{}})
    after['edges'].append({'edge_id':'E','source':'C','target':'H','kind':'weakens'})
    delta=followup_delta(before,after,'run','M','Question','action')
    assert delta['added_node_ids'] == ['C'] and delta['added_edge_ids'] == ['E']
    assert delta['new_weakening_ids'] == ['E'] and delta['reassessed_hypothesis_ids'] == ['H']
    assert delta['previous_resolution'] == 'unresolved' and delta['new_resolution'] == 'partially_answered'
    assert after['followups'] == before['followups'] == [{'run_id':'old'}]


def test_holding_request_reuses_engine_without_manufacturing_anomaly(monkeypatch):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    api=importlib.import_module('investigation_api')
    from unittest.mock import Mock
    from datetime import date
    graph=Mock(investigation_id='holding')
    graph.model_copy.return_value.model_dump.return_value={'nodes':[],'edges':[]}
    engine=Mock(return_value=(graph,None))
    monkeypatch.setattr(api,'investigate_signal',engine)
    monkeypatch.setattr(api,'monitor_pairs',Mock(side_effect=AssertionError('Holding is not a pair anomaly')))
    request={'mode':'holding','ticker_a':'AAA','as_of':'2024-06-28','portfolio':P,**api.public_models()['models'][0]}
    result=api.investigate(request,prices=prices(),fits=[],as_of=date(2026,1,1),formation_observations=252)
    event=engine.call_args.kwargs['event_override']
    assert event.anomaly_type == 'human_research_request'
    assert event.related_entities == ()
    assert 'z_score' not in event.metadata
    assert engine.call_args.kwargs['research_context']['portfolio']['as_of'].startswith('2024-06-28')
    context=[n for n in result['nodes'] if n['kind'] == 'context']
    assert len(context) == 1 and 'not admitted evidence' in context[0]['label']
    assert not any(e['kind'] == 'supports' for e in result['edges'])


def test_simulation_graph_has_price_lineage_and_research_requirement():
    from financial_assistant.portfolio.service import attach_simulation_graph
    result=simulate_overlay(prices(),P,{'ticker_a':'AAA','ticker_b':'BBB'},'2024-06-28')
    graph={'nodes':[],'edges':[]}
    attach_simulation_graph(graph,result,'run')
    calc=next(n for n in graph['nodes'] if n['kind']=='calculation')
    obs=next(n for n in graph['nodes'] if n['kind']=='observation')
    assert any(e['source']==calc['node_id'] and e['target']==obs['node_id'] and e['kind']=='calculated_from' for e in graph['edges'])
    assert calc['data']['formula_version']==VERSION
    assert all(o['date'] <= '2024-06-28' for series in obs['data']['series']['inputs'].values() for o in series)
    assert {e['kind'] for e in graph['edges']} == {'calculated_from','requires'}
