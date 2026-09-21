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
