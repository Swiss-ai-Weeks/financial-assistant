"""Quarterly normalization, accounting semantics and point-in-time contracts."""
from copy import deepcopy
from datetime import datetime, timezone, date
from unittest.mock import Mock
import json
import pytest
from financial_assistant.fundamentals.models import ProviderResponse
from financial_assistant.fundamentals.normalize import CONCEPTS
from financial_assistant.fundamentals.quarterly import quarterly
from financial_assistant.fundamentals.service import FundamentalsService, load_pair, model_context, domain_evidence

CUTOFF = datetime(2026, 3, 1, tzinfo=timezone.utc)


def fixture():
    tags = {}
    for year in (2023, 2024, 2025):
        for q, end in enumerate(('03-31','06-30','09-30','12-31'), 1):
            start = ('01-01','04-01','07-01','10-01')[q-1]
            filing = f'{year}-'+('05-01','08-01','11-01','12-31')[q-1] if q < 4 else f'{year+1}-02-15'
            base = dict(end=f'{year}-{end}', accn=f'0000000001-{year%100:02}-{q:06}', fy=year,
                        fp=f'Q{q}' if q<4 else 'FY', form='10-Q' if q<4 else '10-K', filed=filing)
            for concept, value in (('revenue',100+q+(year-2023)*10),('operating_income',10+q),
                                   ('cash',50+q),('operating_cash_flow',q*20),('capex',q*5)):
                row = dict(base, val=value)
                if concept != 'cash':
                    row['start'] = f'{year}-'+('01-01' if concept in ('operating_cash_flow','capex') else start)
                tags.setdefault(CONCEPTS[concept][0], {'units': {'USD': []}})['units']['USD'].append(row)
    return ProviderResponse(ticker='AAA', cik='0000000001', facts={'entityName':'Fixture','facts':{'us-gaap':tags}}, retrieved_at=CUTOFF)


def test_grouping_instant_discrete_and_ytd_lineage():
    snapshots, facts, calcs, _ = quarterly(fixture(), CUTOFF)
    assert len(snapshots) == 8
    q3 = next(s for s in snapshots if s.fiscal_year == 2025 and s.fiscal_quarter == 'Q3')
    assert q3.period_start == date(2025,7,1)
    indexed = {f.fact_id:f for f in facts}
    cash = indexed[q3.metrics['cash']]
    assert cash.period_start is None and cash.value == 53
    assert indexed[q3.metrics['revenue']].value == 123
    ocf = next(c for c in calcs if c.calculation_id == q3.metrics['operating_cash_flow'])
    assert ocf.value == 20 and len(ocf.input_ids) == 2
    assert {indexed[i].value for i in ocf.input_ids} == {40,60}
    assert all(indexed[i].period_start == date(2025,1,1) for i in ocf.input_ids)
    assert 'net_income' in q3.unavailable_metrics
    assert all(c.available_at is None or c.available_at <= CUTOFF for c in calcs)


def test_qoq_yoy_margins_and_q4():
    snapshots, facts, calcs, _ = quarterly(fixture(), CUTOFF)
    def metric(name):
        return next(c for c in calcs if c.metric_id == name and c.period_end == date(2025,9,30))
    assert metric('revenue_qoq_growth').value == pytest.approx(123/122-1)
    assert metric('revenue_qoq_growth').comparison_period == date(2025,6,30)
    assert metric('revenue_yoy_growth').value == pytest.approx(123/113-1)
    assert metric('revenue_yoy_growth').comparison_period == date(2024,9,30)
    assert metric('operating_margin').value == pytest.approx(13/123)
    assert metric('operating_margin_qoq_change').value == pytest.approx((13/123-12/122)*10000)
    assert metric('free_cash_flow').value == 15
    assert metric('free_cash_flow_margin').value == pytest.approx(15/123)
    q4 = snapshots[-1]
    assert q4.fiscal_quarter == 'Q4'
    assert next(c for c in calcs if c.calculation_id == q4.metrics['operating_cash_flow']).value == 20


def test_future_restatement_does_not_rewrite_history():
    response = fixture()
    raw = deepcopy(response.facts)
    rows = raw['facts']['us-gaap'][CONCEPTS['operating_cash_flow'][0]]['units']['USD']
    rows.append(dict(rows[-2], val=90, filed='2026-04-01', form='10-Q/A', accn='0000000001-26-000099'))
    mutated = response.model_copy(update={'facts':raw})
    assert quarterly(mutated,CUTOFF) == quarterly(response,CUTOFF)
    _, facts, calcs, _ = quarterly(mutated,datetime(2026,5,1,tzinfo=timezone.utc))
    r = next(c for c in calcs if c.metric_id == 'operating_cash_flow_discrete' and c.period_end == date(2025,9,30))
    assert r.value == 50
    assert r.available_at.date() == date(2026,4,1)
    assert any(f.form == '10-Q/A' and f.fact_id in r.input_ids for f in facts)


def test_pair_context_and_full_graph_lineage():
    from financial_assistant.domain import AnomalyEvent, InvestigationState
    from financial_assistant.claimgraph.builder_v2 import build_investigation_graph
    provider = Mock(get_company_facts=lambda ticker, cutoff: fixture().model_copy(update={'ticker':ticker, 'cik':'0000000001' if ticker == 'AAA' else '0000000002'}))
    bundles = load_pair(('AAA','BBB'), CUTOFF, service=FundamentalsService(provider))
    assert all(len(b.snapshots) == 8 for b in bundles)
    docs, obs, calcs = domain_evidence(bundles)
    state = InvestigationState(investigation_id='Q', anomaly=AnomalyEvent(anomaly_id='A', ticker='AAA',
        detected_at=CUTOFF, anomaly_type='pair', summary='Pair'), fundamentals=bundles, documents=docs, observations=obs, calculations=calcs)
    graph = build_investigation_graph(state)
    assert len([n for n in graph.nodes if n.data.get('subtype') == 'fundamental_snapshot']) == 16
    ids = {n.node_id for n in graph.nodes}
    assert all(e.source in ids and e.target in ids for e in graph.edges)
    assert any(e.kind.value == 'extracted_from' and e.source.startswith('observation:') for e in graph.edges)
    assert any(e.kind.value == 'calculated_from' and e.target.startswith('observation:') for e in graph.edges)
    context = model_context(bundles)
    payload = json.loads(context.split('\n',1)[1])
    assert len(payload) == 2 and all(len(b['quarterly_snapshots']) == 8 for b in payload)
    assert 'not causal' in context and 'working capital' in context
    assert 'facts' not in payload[0]
    assert len(payload[0]['trends']) <= 40


def test_missing_comparison_and_zero_denominator():
    response = fixture()
    raw = deepcopy(response.facts)
    rows = raw['facts']['us-gaap'][CONCEPTS['revenue'][0]]['units']['USD']
    for r in rows:
        if r['end'] == '2025-06-30': r['val'] = 0
    _, _, calcs, _ = quarterly(response.model_copy(update={'facts':raw}), CUTOFF)
    for name, end in (('revenue_qoq_growth','2025-09-30'),('operating_margin','2025-06-30')):
        r = next(c for c in calcs if c.metric_id == name and str(c.period_end) == end)
        assert r.status == 'unavailable' and r.value is None


def test_absent_ytd_predecessor_never_becomes_a_quarter():
    response = fixture()
    raw = deepcopy(response.facts)
    rows = raw['facts']['us-gaap'][CONCEPTS['operating_cash_flow'][0]]['units']['USD']
    rows[:] = [r for r in rows if r['end'] != '2025-06-30']
    snapshots, _, calcs, _ = quarterly(response.model_copy(update={'facts':raw}), CUTOFF)
    s = next(s for s in snapshots if str(s.period_end) == '2025-09-30')
    assert 'operating_cash_flow' not in s.metrics
    assert 'operating_cash_flow' in s.unavailable_metrics
    assert not any(c.metric_id == 'operating_cash_flow_discrete' and c.period_end == s.period_end for c in calcs)


def test_noncalendar_fiscal_year_and_comparative_filing_labels():
    response = fixture()
    raw = deepcopy(response.facts)
    # Shift an entire reporting calendar by six months, preserving fiscal labels.
    for tag in raw['facts']['us-gaap'].values():
        for row in tag['units']['USD']:
            for key in ('start','end','filed'):
                if key in row:
                    d = date.fromisoformat(row[key])
                    if key == 'end':
                        import calendar
                        month = (d.month+5)%12+1
                        row[key] = str(date(d.year+(d.month>6),month,calendar.monthrange(d.year+(d.month>6),month)[1]))
                    else:
                        row[key] = str(date(d.year+(d.month>6),(d.month+5)%12+1,min(d.day,28)))
    snapshots, _, _, _ = quarterly(response.model_copy(update={'facts':raw}), datetime(2027,3,1,tzinfo=timezone.utc))
    s = next(s for s in snapshots if s.period_end == date(2026,3,31))
    assert s.fiscal_year == 2025 and s.fiscal_quarter == 'Q3'
    assert s.period_start == date(2026,1,1)


def test_quarterly_service_exclusion_and_serialized_replay():
    from financial_assistant.fundamentals.models import FundamentalEvidenceBundle
    response = fixture()
    provider = Mock(get_company_facts=Mock(return_value=response))
    b = FundamentalsService(provider).calculate_metrics('AAA',CUTOFF,frequency='quarterly',periods=8)
    assert len(b.snapshots) == 8 and provider.get_company_facts.call_count == 1
    assert FundamentalEvidenceBundle.model_validate_json(b.model_dump_json()) == b
    provider.get_company_facts.return_value = response.model_copy(update={'submissions':{'sic':'6311'}})
    excluded = FundamentalsService(provider).quarterly_metrics('AAA',CUTOFF)
    assert excluded.status == 'unavailable' and not excluded.snapshots and not excluded.facts


def test_standalone_quarter_without_ytd_anchor_and_q4_income_difference():
    response = fixture()
    raw = deepcopy(response.facts)
    # Only a standalone Q2 revenue fact remains. It is not an annual value.
    raw['facts']['us-gaap'] = {CONCEPTS['revenue'][0]: {'units': {'USD': [
        dict(end='2025-06-30', start='2025-04-01', val=123, fy=2025, fp='Q2',
             filed='2025-08-01', form='10-Q', accn='0000000001-25-000002')]}}}
    snapshots, facts, _, _ = quarterly(response.model_copy(update={'facts':raw}),CUTOFF)
    assert len(snapshots) == 1 and snapshots[0].fiscal_quarter == 'Q2'
    assert facts[0].value == 123
    raw = deepcopy(response.facts)
    rows = raw['facts']['us-gaap'][CONCEPTS['revenue'][0]]['units']['USD']
    q3 = next(r for r in rows if r['end'] == '2025-09-30')
    rows.append(dict(q3, start='2025-01-01', val=360))
    for row in rows:
        if row['end'] == '2025-12-31':
            row.update(start='2025-01-01',val=490)
    snapshots, facts, calcs, _ = quarterly(response.model_copy(update={'facts':raw}),CUTOFF)
    s = snapshots[-1]
    r = next(c for c in calcs if c.calculation_id == s.metrics['revenue'])
    assert r.value == 130 and len(r.input_fact_ids) == 2
    # Direct Q3 revenue wins over its cumulative value.
    s = snapshots[-2]
    assert next(f.value for f in facts if f.fact_id == s.metrics['revenue']) == 123
