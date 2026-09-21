"""Allow-listed application formulas. No model or provider supplies arithmetic."""
from dataclasses import dataclass
from datetime import timedelta
import math
from .models import MetricResult
from .normalize import stable_id


@dataclass(frozen=True)
class Definition:
    formula: str
    inputs: tuple[str, ...]
    unit: str = 'ratio'
    name: str = ''
    warnings: tuple[str, ...] = ()


def d(formula, inputs, unit='ratio', name='', warnings=()):
    return Definition(formula, tuple(inputs.split()), unit, name, warnings)


REGISTRY = {
    'revenue_growth_yoy': d('revenue / prior comparable revenue - 1', 'revenue'),
    'operating_margin': d('operating_income / revenue', 'operating_income revenue'),
    'net_margin': d('net_income / revenue', 'net_income revenue'),
    'operating_cash_flow_margin': d('operating_cash_flow / revenue', 'operating_cash_flow revenue'),
    'capex_outflow': d('capex (positive payments convention)', 'capex', 'USD'),
    'free_cash_flow': d('operating_cash_flow - capex_outflow', 'operating_cash_flow capex_outflow', 'USD'),
    'free_cash_flow_margin': d('free_cash_flow / revenue', 'free_cash_flow revenue'),
    'cash_conversion_or_cfo_to_net_income': d('operating_cash_flow / net_income', 'operating_cash_flow net_income'),
    'total_debt': d('reported debt including finance/capital leases OR short_term_debt + current_long_term_debt + long_term_debt + finance_lease_current + finance_lease_noncurrent', 'total_debt short_term_debt current_long_term_debt long_term_debt finance_lease_current finance_lease_noncurrent', 'USD', warnings=('Debt includes finance/capital leases; operating leases are excluded from the constructed debt definition. All components, including zero balances, must be reported.',)),
    'net_debt': d('total_debt - cash', 'total_debt cash', 'USD'),
    'derived_ebitda': d('operating_income + depreciation_and_amortization', 'operating_income depreciation_and_amortization', 'USD', 'Derived EBITDA', ('Operating income is an EBIT proxy; D&A may include depletion.',)),
    'net_debt_to_ebitda': d('net_debt / derived_ebitda', 'net_debt derived_ebitda', 'multiple'),
    'interest_coverage': d('operating_income / interest_expense', 'operating_income interest_expense', 'multiple', warnings=('Operating income is an EBIT proxy.',)),
    'capex_to_revenue': d('capex_outflow / revenue', 'capex_outflow revenue'),
    'working_capital': d('current_assets - current_liabilities', 'current_assets current_liabilities', 'USD'),
    'working_capital_to_revenue': d('working_capital / revenue', 'working_capital revenue'),
    'average_assets': d('(beginning total_assets + ending total_assets) / 2', 'total_assets', 'USD'),
    'asset_turnover': d('revenue / average_assets', 'revenue average_assets', 'multiple'),
    'effective_tax_rate': d('tax_expense / pretax_income; pretax > 0 and 0 <= rate <= 1', 'tax_expense pretax_income'),
    'nopat': d('operating_income * (1 - effective_tax_rate)', 'operating_income effective_tax_rate', 'USD'),
    'invested_capital': d('shareholders_equity + total_debt - cash', 'shareholders_equity total_debt cash', 'USD'),
    'average_invested_capital': d('(beginning invested_capital + ending invested_capital) / 2', 'invested_capital', 'USD'),
    'roic': d('NOPAT / average(beginning, ending invested capital); invested capital = equity + debt - cash', 'nopat average_invested_capital', name='ROIC', warnings=('Industrial ROIC-v1 is one definition, not a universal accounting standard.',)),
    'share_dilution_yoy': d('diluted_shares / prior comparable diluted_shares - 1', 'diluted_shares'),
}
DEFAULT_METRICS = tuple('revenue_growth_yoy operating_margin free_cash_flow free_cash_flow_margin cash_conversion_or_cfo_to_net_income net_debt net_debt_to_ebitda interest_coverage capex_to_revenue asset_turnover roic share_dilution_yoy'.split())
PUBLIC_METRICS = DEFAULT_METRICS + ('net_margin', 'operating_cash_flow_margin', 'working_capital_to_revenue')
INDUSTRIAL = {'roic', 'net_debt_to_ebitda', 'derived_ebitda', 'interest_coverage', 'invested_capital', 'average_invested_capital', 'nopat'}


class Unavailable(Exception):
    pass


def calculate(facts, periods, *, ticker, frequency='annual', metrics=DEFAULT_METRICS, financial_institution=False):
    unknown = set(metrics) - REGISTRY.keys()
    if unknown:
        raise ValueError(f'Unknown metrics: {sorted(unknown)}')
    index = {(f.concept, f.period_end): f for f in facts}
    results = {}

    def compute(metric, end):
        key = (metric, end)
        if key in results:
            return results[key]
        definition = REGISTRY[metric]
        inputs = []
        raw_inputs = []
        reason = None
        status = 'available'
        value = None

        def get(concept, at=end):
            if concept in REGISTRY:
                result = compute(concept, at)
                if result.status != 'available':
                    raise Unavailable(f'{concept}: {result.unavailable_reason}')
                inputs.append(result)
                raw_inputs.extend(indexed_facts[i] for i in result.input_fact_ids)
                return result.value
            fact = index.get((concept, at))
            if fact is None:
                raise Unavailable(f'Missing {concept} at {at}')
            inputs.append(fact)
            raw_inputs.append(fact)
            return fact.value

        def divide(a, b):
            if b <= 0:
                raise Unavailable('Denominator must be positive; ratio not meaningful')
            return a / b

        def beginning():
            anchors = [f.period_start for f in facts if f.period_end == end and f.period_start]
            if not anchors or len(set(anchors)) != 1:
                raise Unavailable('Unambiguous duration start required for beginning balance')
            return anchors[0] - timedelta(days=1)

        def prior(concept):
            current = index.get((concept, end))
            if current is None or current.period_start is None:
                raise Unavailable(f'Missing current {concept}')
            candidates = [f for f in facts if f.concept == concept and
                          350 <= (end - f.period_end).days <= 380 and f.period_start and
                          abs((end-current.period_start).days-(f.period_end-f.period_start).days) <= 7]
            if len(candidates) != 1:
                raise Unavailable('Missing unambiguous prior comparable period')
            return candidates[0].period_end

        try:
            if financial_institution and metric in INDUSTRIAL:
                status = 'not_applicable'
                raise Unavailable('Industrial-company formula is not applicable to financial institutions')
            if frequency == 'quarterly' and metric == 'net_debt_to_ebitda':
                raise Unavailable('Annual EBITDA required; quarterly EBITDA is not annualized')
            if metric == 'total_debt':
                fact = index.get(('total_debt', end))
                if fact:
                    inputs.append(fact)
                    raw_inputs.append(fact)
                    value = fact.value
                else:
                    value = (get('short_term_debt') + get('current_long_term_debt') + get('long_term_debt')
                             + get('finance_lease_current') + get('finance_lease_noncurrent'))
            elif metric == 'capex_outflow':
                value = get('capex')
                if value < 0:
                    raise Unavailable('Negative SEC payments value: capex sign is ambiguous; not silently inverted')
            elif metric in ('revenue_growth_yoy', 'share_dilution_yoy'):
                concept = 'revenue' if metric == 'revenue_growth_yoy' else 'diluted_shares'
                value = divide(get(concept), get(concept, prior(concept))) - 1
            elif metric in ('average_assets', 'average_invested_capital'):
                concept = 'total_assets' if metric == 'average_assets' else 'invested_capital'
                value = (get(concept, beginning()) + get(concept)) / 2
            elif metric == 'nopat':
                value = get('operating_income') * (1 - get('effective_tax_rate'))
            elif metric == 'invested_capital':
                value = get('shareholders_equity') + get('total_debt') - get('cash')
            else:
                left, right = (get(c) for c in definition.inputs)
                if metric in ('free_cash_flow', 'net_debt', 'working_capital'):
                    value = left - right
                elif metric == 'derived_ebitda':
                    if right < 0:
                        raise Unavailable('Negative D&A is unsuitable for derived EBITDA')
                    value = left + right
                else:
                    value = divide(left, right)
                    if metric == 'effective_tax_rate' and not 0 <= value <= 1:
                        raise Unavailable('Reported effective tax rate outside [0, 1]')
            # Current-period duration inputs must have the same exact context.
            durations = {(f.period_start, f.period_end) for f in raw_inputs if f.period_start and f.period_end == end}
            if len(durations) > 1:
                raise Unavailable('Incompatible duration contexts')
            if not math.isfinite(value):
                raise Unavailable('Non-finite result')
        except Unavailable as exc:
            reason = str(exc)
            status = 'unavailable' if status == 'available' else status
            value = None
            inputs = []
            raw_inputs = []
        ids = tuple(dict.fromkeys(getattr(i, 'fact_id', None) or i.calculation_id for i in inputs))
        fact_ids = tuple(sorted({f.fact_id for f in raw_inputs}))
        version = f'{metric.replace("_", "-")}-v1'
        result = MetricResult(calculation_id=stable_id('FIN', ticker, metric, end, frequency, version, ids),
                              metric_id=metric, display_name=definition.name or metric.replace('_', ' ').title(),
                              formula_version=version, formula=definition.formula, required_inputs=definition.inputs,
                              period_end=end, frequency=frequency, value=value, unit=definition.unit,
                              input_ids=ids, input_fact_ids=fact_ids,
                              available_at=max((f.available_at for f in raw_inputs), default=None),
                              status=status, unavailable_reason=reason, warnings=tuple(dict.fromkeys(definition.warnings + tuple(w for i in inputs if isinstance(i, MetricResult) for w in i.warnings))) +
                              (('Quarterly flows and returns are not annualized.',) if frequency == 'quarterly' else ()))
        results[key] = result
        return result

    indexed_facts = {f.fact_id: f for f in facts}
    for period in periods:
        for metric in metrics:
            compute(metric, period)
    # Keep only requested calculations and transitive inputs actually used by
    # available results. Unsuccessful intermediate attempts are not evidence.
    roots = [results[m, p] for p in periods for m in metrics]
    by_id = {r.calculation_id: r for r in results.values()}
    retained = {}

    def retain(result):
        if result.calculation_id in retained:
            return
        retained[result.calculation_id] = result
        if result.status == 'available':
            for identifier in result.input_ids:
                if identifier in by_id:
                    retain(by_id[identifier])
    for root in roots:
        retain(root)
    return tuple(retained.values())


def trends(calculations, ticker):
    """Endpoint changes across >=3 contiguous annual periods, not causal findings."""
    results = []
    for metric in ('operating_margin', 'roic', 'free_cash_flow_margin', 'net_debt'):
        series = sorted((c for c in calculations if c.metric_id == metric and c.status == 'available'), key=lambda c: c.period_end)
        if len(series) < 3 or any(not 350 <= (b.period_end-a.period_end).days <= 380 for a, b in zip(series, series[1:])):
            continue
        first, last = series[0], series[-1]
        if metric == 'net_debt':
            if first.value <= 0 or last.value < 0:
                continue
            value, unit, formula = (last.value/first.value-1)*100, 'percent', '(last / first - 1) * 100'
        else:
            value, unit, formula = (last.value-first.value)*10000, 'bps', '(last - first) * 10000'
        results.append(MetricResult(
            calculation_id=stable_id('TREND', ticker, first.calculation_id, last.calculation_id),
            metric_id=f'{metric}_trend', display_name=f'{metric} change over {len(series)} annual periods',
            formula_version='endpoint-trend-v1', formula=formula, period_end=last.period_end,
            frequency='annual', value=value, unit=unit, input_ids=(first.calculation_id, last.calculation_id),
            input_fact_ids=tuple(sorted(set(first.input_fact_ids + last.input_fact_ids))),
            available_at=max(first.available_at, last.available_at), warnings=('Descriptive change, not a causal explanation.',)))
    return tuple(results)
