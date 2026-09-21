"""Compact market context and graph projection, using the existing price cache."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from .returns import security_returns, SOURCE, VERSION


def market_context(tickers, as_of, prices=None):
    if prices is None:
        path = Path(SOURCE)
        if not path.exists():
            return {'status': 'unavailable', 'reason': 'Historical market cache unavailable'}
        prices = pd.read_csv(path)
    securities = {t: security_returns(prices, t, as_of) for t in dict.fromkeys(tickers)}
    relative = {}
    if len(securities) == 2:
        a, b = securities.values()
        for n in (20, 63):
            x, y = a.get(f'return_{n}', {}), b.get(f'return_{n}', {})
            # Relative endpoints must be identical; never compare asynchronous windows.
            if x.get('status') == y.get('status') == 'available' and [i['date'] for i in x['inputs']] == [i['date'] for i in y['inputs']]:
                relative[str(n)] = dict(value=x['value']-y['value'], unit='ratio', formula='return_A - return_B', formula_version=VERSION)
    return dict(status='available', securities=securities, relative_returns=relative,
                interpretation='Deterministic descriptive calculations, not causal evidence. Do not calculate additional returns with the model.')


def attach_market_graph(graph, context):
    """Only endpoint observations and meaningful returns render; no daily-series explosion."""
    nodes, edges = [], []
    seen = set()
    for ticker, security in context.get('securities', {}).items():
        for key in ('return_1', 'return_5', 'return_20', 'return_63'):
            calculation = security.get(key, {})
            if calculation.get('status') != 'available':
                continue
            cid = 'calculation:market-' + hashlib.sha256(json.dumps(calculation, sort_keys=True).encode()).hexdigest()[:20]
            nodes.append(dict(node_id=cid, kind='calculation', label=f'{ticker} {key.replace("_", " ")}: {calculation["value"]:.2%}',
                              data={**calculation, 'expression': calculation['formula'], 'metadata': {'ticker': ticker}}))
            for obs in calculation['inputs']:
                oid = 'observation:price-' + hashlib.sha256(json.dumps(obs, sort_keys=True).encode()).hexdigest()[:20]
                if oid not in seen:
                    seen.add(oid)
                    nodes.append(dict(node_id=oid, kind='observation', label=f'{ticker} close · {obs["date"]}',
                                      data={**obs, 'published_at': obs['date']+'T23:59:59Z'}))
                edges.append(dict(edge_id=cid+'-'+oid, source=cid, target=oid, kind='calculated_from', data={}))
    graph['nodes'].extend(nodes)
    graph['edges'].extend(edges)
    return graph


def attach_simulation_graph(graph, simulation, run_id):
    inputs_id = f'observation:simulation-inputs-{run_id}'
    graph['nodes'].append(dict(node_id=inputs_id, kind='observation', label='Historical price inputs (compact series)',
        data={'published_at': simulation['current']['end']+'T23:59:59Z', 'series': simulation['provenance'],
              'interpretation': 'Compact collection of dated price observations, not an economic claim'}))
    calc_id = f'calculation:simulation-{run_id}'
    graph['nodes'].append(dict(node_id=calc_id, kind='calculation', label='Historical portfolio overlay simulation',
        data={k: v for k, v in simulation.items() if k != 'provenance'}))
    graph['edges'].append(dict(edge_id=f'{calc_id}-inputs', source=calc_id, target=inputs_id, kind='calculated_from', data={}))
    graph['edges'].append(dict(edge_id=f'{calc_id}-question', source=calc_id, target=f'missing:simulation-{run_id}', kind='requires', data={}))
