"""Quarter contexts and deterministic arithmetic; raw SEC facts are never rewritten."""
from datetime import timedelta
import math
from .models import FundamentalSnapshot, MetricResult
from .normalize import CONCEPTS, INSTANT, normalize, stable_id

CORE = tuple('revenue gross_profit operating_income net_income interest_expense eps cash current_assets total_assets current_liabilities total_debt shareholders_equity shares_outstanding diluted_shares operating_cash_flow capex investing_cash_flow financing_cash_flow'.split())
MARGINS = {'gross_margin': 'gross_profit', 'operating_margin': 'operating_income', 'net_margin': 'net_income', 'free_cash_flow_margin': 'free_cash_flow'}


def quarterly(response, cutoff, limit=8):
    facts, warnings = normalize(response, cutoff, 'quarterly', cumulative=True)
    by_id = {f.fact_id: f for f in facts}
    # Fiscal labels on comparative facts refer to the filing, not the fact.
    # Use contemporaneous duration contexts only to establish fiscal anchors.
    anchors = {}
    anchor_facts, _ = normalize(response, cutoff, 'quarterly', cumulative=True, all_versions=True)
    for f in anchor_facts:
        if not f.period_start or (f.filed_at-f.period_end).days > 180:
            continue
        days = (f.period_end-f.period_start).days + 1
        q = next((q for q, lo, hi in ((1,80,100),(2,170,195),(3,260,290),(4,350,380)) if lo <= days <= hi), None)
        if q and f.fiscal_period == ('FY' if q == 4 else f'Q{q}') and f.fiscal_year:
            anchors.setdefault(f.period_start, set()).add(f.fiscal_year)
    anchors = {s: next(iter(years)) for s, years in anchors.items() if len(years) == 1}
    contexts = {}
    for f in facts:
        if not f.period_start:
            continue
        options = []
        for start, year in anchors.items():
            days = (f.period_end-start).days + 1
            q = next((q for q, lo, hi in ((1,80,100),(2,170,195),(3,260,290),(4,350,380)) if lo <= days <= hi), None)
            if q and start <= f.period_start:
                options.append((start, year, q))
        if len(options) != 1:
            continue
        start, year, q = options[0]
        contexts[f.period_end] = (start, year, q)
    # A standalone quarter can still be grouped when a fiscal-start/YTD anchor
    # is absent. Do not invent a fiscal-year start for subtraction in that case.
    standalone = {}
    for f in anchor_facts:
        if (not f.period_start or not f.fiscal_year or (f.filed_at-f.period_end).days > 180
                or not 80 <= (f.period_end-f.period_start).days+1 <= 100):
            continue
        q = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'FY': 4}.get(f.fiscal_period)
        if q:
            standalone.setdefault(f.period_end, set()).add((f.fiscal_year, q, f.period_start))
    for end, choices in standalone.items():
        if end not in contexts and len(choices) == 1:
            year, q, _ = next(iter(choices))
            contexts[end] = (None, year, q)
    values, starts, derivations = {}, {}, []

    def result(metric, end, inputs, formula, value, unit='USD', comparison=None, reason=None):
        ids = tuple(getattr(i, 'fact_id', None) or i.calculation_id for i in inputs)
        raw_ids = tuple(sorted({fid for i in inputs for fid in ((i.fact_id,) if hasattr(i, 'fact_id') else i.input_fact_ids)}))
        version = f'{metric.replace("_", "-")}-quarterly-v1'
        if value is not None and not math.isfinite(value):
            value, reason = None, 'Non-finite result'
        r = MetricResult(calculation_id=stable_id('FIN', response.ticker, metric, end, version, ids), metric_id=metric,
            display_name=metric.replace('_', ' ').title(), formula_version=version, formula=formula,
            required_inputs=tuple(getattr(i, 'concept', None) or i.metric_id for i in inputs),
            period_end=end, frequency='quarterly', comparison_period=comparison, value=value, unit=unit,
            input_ids=ids, input_fact_ids=raw_ids, available_at=max((i.available_at for i in inputs if i.available_at is not None), default=None),
            status='available' if value is not None else 'unavailable', unavailable_reason=reason,
            warnings=('Descriptive accounting evidence; not a causal explanation. Quarterly flows are not annualized.',))
        derivations.append(r)
        return r

    for end, (fy_start, year, q) in sorted(contexts.items()):
        preceding = [e for e, (s, y, n) in contexts.items() if s == fy_start and y == year and n == q-1]
        start = fy_start if q == 1 else (max(preceding)+timedelta(days=1) if preceding else None)
        discrete = [f for f in facts if f.period_end == end and f.period_start and 80 <= (end-f.period_start).days+1 <= 100]
        if start is None and discrete and len({f.period_start for f in discrete}) == 1:
            start = discrete[0].period_start
        if start is None or not 80 <= (end-start).days+1 <= 100:
            continue
        starts[end] = start
        for concept in CONCEPTS:
            candidates = [f for f in facts if f.concept == concept and f.period_end == end and
                          f.period_start == (None if concept in INSTANT else start)]
            if len(candidates) == 1:
                values[concept, end] = candidates[0]
                continue
            # Weighted averages and per-share quantities cannot be subtracted.
            if concept in INSTANT or 'shares' in concept or concept == 'eps':
                continue
            current = [f for f in facts if f.concept == concept and f.period_start == fy_start and f.period_end == end]
            prior = [f for f in facts if f.concept == concept and f.period_start == fy_start and f.period_end == start-timedelta(days=1)]
            if len(current) == len(prior) == 1 and current[0].tag == prior[0].tag and current[0].unit == prior[0].unit:
                a, b = current[0], prior[0]
                values[concept, end] = result(concept+'_discrete', end, [a,b], 'current YTD - preceding YTD (same fiscal start, taxonomy concept and unit)', a.value-b.value, comparison=b.period_end)
    ends = sorted(starts)[-limit:]
    for end in sorted(starts):
        def derive(name, inputs, formula, operation, unit='USD', positive=False):
            items = [values.get((i, end)) for i in inputs]
            reason = 'Missing required inputs: ' + ', '.join(i for i, v in zip(inputs, items) if v is None or v.value is None)
            valid = all(i is not None and i.value is not None for i in items)
            if valid and positive and items[-1].value <= 0:
                valid, reason = False, 'Denominator must be positive'
            if valid and name == 'free_cash_flow' and items[1].value < 0:
                valid, reason = False, 'Negative capex payments convention is ambiguous'
            r = result(name, end, [i for i in items if i is not None], formula,
                       operation(*(i.value for i in items)) if valid else None, unit, reason=None if valid else reason)
            values[name, end] = r
        if ('total_debt', end) not in values:
            derive('total_debt', ('short_term_debt','current_long_term_debt','long_term_debt','finance_lease_current','finance_lease_noncurrent'), 'sum of reported debt and finance lease components; no missing component assumed zero', lambda *x: sum(x))
        derive('free_cash_flow', ('operating_cash_flow','capex'), 'operating_cash_flow - capex', lambda a,b:a-b)
        derive('net_debt', ('total_debt','cash'), 'total_debt - cash', lambda a,b:a-b)
        for margin, numerator in MARGINS.items():
            derive(margin, (numerator,'revenue'), numerator+' / revenue', lambda a,b:a/b, 'ratio', True)
    for end in ends:
        year, q = contexts[end][1:]
        for cadence, offset in (('qoq',1), ('yoy',4)):
            prior_ends = [e for e in starts if contexts[e][1]*4+contexts[e][2] == year*4+q-offset
                          and (70 <= (end-e).days <= 110 if offset == 1 else 350 <= (end-e).days <= 380)]
            previous = prior_ends[0] if len(prior_ends) == 1 else None
            for metric in ('revenue','operating_cash_flow','capex','cash','net_debt','shares_outstanding','diluted_shares', *MARGINS):
                a, b = values.get((metric,end)), values.get((metric,previous))
                valid = a is not None and b is not None and a.value is not None and b.value is not None
                inputs = [i for i in (a,b) if i is not None]
                margin = metric in MARGINS
                result(f'{metric}_{cadence}_change', end, inputs, '(current - comparison) * 10000' if margin else 'current - comparison',
                       (a.value-b.value)*(10000 if margin else 1) if valid else None,
                       'bps' if margin else ('shares' if 'shares' in metric else 'USD'), previous,
                       None if valid else 'Missing comparable fiscal quarter or metric')
                if not margin:
                    valid = valid and b.value > 0
                    result(f'{metric}_{cadence}_growth', end, inputs, 'current / comparison - 1; comparison > 0',
                           a.value/b.value-1 if valid else None, 'ratio', previous,
                           None if valid else 'Missing comparison or nonpositive denominator')
    snapshots = []
    for end in ends:
        metrics = {m: getattr(v, 'fact_id', None) or v.calculation_id for (m,e), v in values.items() if e == end and v.value is not None}
        unavailable = {m: 'No reliable discrete quarter or instant value' for m in (*CORE, *MARGINS, 'free_cash_flow', 'net_debt') if m not in metrics}
        used = {fid for identifier in metrics.values() for fid in ((identifier,) if identifier in by_id else next(c.input_fact_ids for c in derivations if c.calculation_id == identifier))}
        filings = {by_id[i].accession: {'accession':by_id[i].accession, 'filing_date':str(by_id[i].filed_at), 'form':by_id[i].form} for i in used}
        snapshots.append(FundamentalSnapshot(snapshot_id=stable_id('SNAPSHOT',response.ticker,end), entity=response.ticker,
            fiscal_year=contexts[end][1], fiscal_quarter=f'Q{contexts[end][2]}', period_start=starts[end], period_end=end,
            availability_cutoff=cutoff, available_at=max((by_id[i].available_at for i in used), default=None),
            metrics=metrics, unavailable_metrics=unavailable, filings=tuple(filings[k] for k in sorted(filings))))
    # Keep transitive comparison and YTD inputs, but bound the public series to eight quarters.
    calculations = {c.calculation_id:c for c in derivations}
    retained = set()
    def retain(identifier):
        if identifier in retained:
            return
        retained.add(identifier)
        if identifier in calculations:
            for i in calculations[identifier].input_ids:
                retain(i)
    for s in snapshots:
        for i in s.metrics.values():
            retain(i)
    for c in derivations:
        if c.period_end in ends:
            retain(c.calculation_id)
    return tuple(snapshots), tuple(f for f in facts if f.fact_id in retained), tuple(c for c in derivations if c.calculation_id in retained), warnings
