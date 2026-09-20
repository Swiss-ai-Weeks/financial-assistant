"""Offline SEC-shaped facts, finance formula, lineage and replay contracts."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from financial_assistant.fundamentals.models import ProviderResponse
from financial_assistant.fundamentals.normalize import CONCEPTS, normalize
from financial_assistant.fundamentals.metrics import REGISTRY, PUBLIC_METRICS, calculate
from financial_assistant.fundamentals.service import FundamentalsService, domain_evidence, load_pair, model_context
from financial_assistant.domain import AnomalyEvent, InvestigationState
from financial_assistant.claimgraph.builder_v2 import build_investigation_graph
from financial_assistant.claimgraph.schema_v2 import InvestigationGraph

FIXTURES = Path(__file__).parent / 'fixtures/fundamentals'
D = datetime(2024, 3, 1, tzinfo=timezone.utc)
END = date(2022, 12, 31)


@pytest.fixture
def response():
    return ProviderResponse(ticker='AAA', cik='0000000001',
        facts=json.loads((FIXTURES/'companyfacts.json').read_text()),
        submissions=json.loads((FIXTURES/'submissions.json').read_text()), retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc))


def facts_at(response, cutoff=D, frequency='annual'):
    return normalize(response, cutoff, frequency)[0]


def find(facts, concept, end=END):
    return next(f for f in facts if f.concept == concept and f.period_end == end)


def test_cutoff_restated_and_amended(response):
    assert find(facts_at(response), 'revenue').value == 1000
    assert find(facts_at(response, datetime(2025, 3, 1, tzinfo=timezone.utc)), 'revenue').value == 1500
    amended = find(facts_at(response, datetime(2025, 6, 1, tzinfo=timezone.utc)), 'revenue')
    assert amended.value == 1700 and amended.form == '10-K/A'
    assert amended.accession == '0000000001-25-000002'


def test_period_end_is_not_availability_and_intraday_is_conservative(response):
    for cutoff in (datetime(2026, 1, 15, tzinfo=timezone.utc), datetime(2026, 2, 20, 21, tzinfo=timezone.utc)):
        assert not any(f.period_end.year == 2025 for f in facts_at(response, cutoff))
    assert any(f.period_end.year == 2025 for f in facts_at(response, datetime(2026, 2, 21, tzinfo=timezone.utc)))


def test_future_mutations_cannot_change_past(response):
    before = facts_at(response)
    raw = deepcopy(response.facts)
    for tag in raw['facts']['us-gaap'].values():
        for rows in tag['units'].values():
            for row in rows:
                if row['filed'] > D.date().isoformat():
                    row['val'] *= 10000
    mutated = response.model_copy(update={'facts':raw})
    assert facts_at(mutated) == before
    assert calculate(before, (END,), ticker='AAA') == calculate(facts_at(mutated), (END,), ticker='AAA')


def test_alias_priority_missing_units_and_full_provenance(response):
    revenue = find(facts_at(response), 'revenue')
    assert revenue.tag == CONCEPTS['revenue'][0] and revenue.value == 1000 and revenue.unit == 'USD'
    assert revenue.period_start == date(2022,1,1) and revenue.fiscal_year == 2022
    assert revenue.filed_at == date(2023,2,20) and revenue.retrieved_at.year == 2026
    raw = deepcopy(response.facts)
    del raw['facts']['us-gaap'][CONCEPTS['revenue'][0]]
    assert find(facts_at(response.model_copy(update={'facts':raw})), 'revenue').tag == 'Revenues'
    del raw['facts']['us-gaap']['Revenues']['units']['USD']
    assert not any(f.concept == 'revenue' for f in facts_at(response.model_copy(update={'facts':raw})))


def test_quarter_does_not_use_ytd_or_annual(response):
    facts = facts_at(response, datetime(2024,9,1,tzinfo=timezone.utc), 'quarterly')
    end = date(2024,6,30)
    assert find(facts, 'operating_income', end).value == 55
    assert not any(f.concept == 'operating_cash_flow' for f in facts)
    result = calculate(facts, (end,), ticker='AAA', frequency='quarterly', metrics=('free_cash_flow',))[0]
    assert result.status == 'unavailable'


EXPECTED = {
    'revenue_growth_yoy': 1000/900-1, 'operating_margin': .2, 'net_margin': .12,
    'operating_cash_flow_margin': .18, 'capex_outflow': 60, 'free_cash_flow': 120,
    'free_cash_flow_margin': .12, 'cash_conversion_or_cfo_to_net_income': 1.5,
    'total_debt': 300, 'net_debt': 200, 'derived_ebitda': 240,
    'net_debt_to_ebitda': 200/240, 'interest_coverage': 10, 'capex_to_revenue': .06,
    'working_capital': 200, 'working_capital_to_revenue': .2,
    'average_assets': 950, 'asset_turnover': 1000/950, 'effective_tax_rate': .25,
    'nopat': 150, 'invested_capital': 800, 'average_invested_capital': 760,
    'roic': 150/760, 'share_dilution_yoy': 100/90-1,
}


@pytest.mark.parametrize('metric', sorted(REGISTRY))
def test_every_formula_directly(response, metric):
    result = next(c for c in calculate(facts_at(response), (END,), ticker='AAA', metrics=(metric,)) if c.metric_id == metric and c.period_end == END)
    assert result.status == 'available', result.unavailable_reason
    assert result.value == pytest.approx(EXPECTED[metric], rel=1e-10, abs=1e-12)
    assert result.formula_version and result.input_fact_ids and result.available_at <= D


def test_roic_full_lineage_and_debt_components(response):
    bundle = FundamentalsService(Mock(get_company_facts=Mock(return_value=response))).calculate_metrics('AAA', D)
    by_id = {r.calculation_id:r for r in bundle.calculations}
    roic = next(r for r in bundle.calculations if r.metric_id == 'roic' and r.period_end == END)
    assert roic.formula_version == 'roic-v1'
    assert {by_id[i].metric_id for i in roic.input_ids} == {'nopat', 'average_invested_capital'}
    debt = next(r for r in bundle.calculations if r.metric_id == 'total_debt' and r.period_end == END)
    facts = {f.fact_id:f for f in bundle.facts}
    assert {facts[i].concept for i in debt.input_ids} == {'short_term_debt', 'current_long_term_debt', 'long_term_debt', 'finance_lease_current', 'finance_lease_noncurrent'}


@pytest.mark.parametrize('concept,value', [('pretax_income',-1), ('pretax_income',0), ('tax_expense',-10), ('tax_expense',300)])
def test_unsuitable_tax_rate(response, concept, value):
    facts = tuple(f.model_copy(update={'value':value}) if f.concept == concept else f for f in facts_at(response))
    result = calculate(facts, (END,), ticker='AAA', metrics=('roic',))[0]
    assert result.status == 'unavailable' and result.value is None


@pytest.mark.parametrize('missing', ['short_term_debt', 'current_long_term_debt', 'long_term_debt', 'finance_lease_current', 'finance_lease_noncurrent'])
def test_missing_debt_is_not_zero(response, missing):
    facts = tuple(f for f in facts_at(response) if f.concept != missing)
    result = calculate(facts, (END,), ticker='AAA', metrics=('net_debt',))[0]
    assert result.status == 'unavailable' and missing in result.unavailable_reason


def test_reported_debt_and_capex_sign(response):
    facts = facts_at(response)
    template = find(facts, 'cash')
    facts += (template.model_copy(update={'fact_id':'reported-debt','concept':'total_debt','value':400}),)
    result = calculate(facts, (END,), ticker='AAA', metrics=('net_debt',))[0]
    assert result.value == 300
    facts = tuple(f.model_copy(update={'value':-60}) if f.concept == 'capex' else f for f in facts)
    result = calculate(facts, (END,), ticker='AAA', metrics=('free_cash_flow','operating_margin'))
    assert result[0].status == 'unavailable' and result[1].value == .2


@pytest.mark.parametrize('metric,concept', [('net_debt_to_ebitda','operating_income'), ('cash_conversion_or_cfo_to_net_income','net_income'), ('interest_coverage','interest_expense')])
def test_unsuitable_denominators(response, metric, concept):
    facts = tuple(f.model_copy(update={'value':-100}) if f.concept == concept else f for f in facts_at(response))
    assert calculate(facts, (END,), ticker='AAA', metrics=(metric,))[0].status == 'unavailable'


def test_financial_institutions(response):
    provider = Mock(get_company_facts=Mock(return_value=response.model_copy(update={'submissions':{'sic':'6021'}})))
    bundle = FundamentalsService(provider).calculate_metrics('AAA', D)
    for result in bundle.calculations:
        if result.metric_id in ('roic','net_debt_to_ebitda','interest_coverage'):
            assert result.status == 'not_applicable'
    assert any(r.status == 'available' for r in bundle.calculations)


def test_pair_graph_and_replay_offline(response, monkeypatch):
    def get(ticker, as_of):
        assert as_of == D
        return response.model_copy(update={'ticker':ticker,'cik':'0000000001' if ticker == 'AAA' else '0000000002'})
    provider = Mock(get_company_facts=get)
    bundles = load_pair(('AAA','BBB'), D, service=FundamentalsService(provider))
    documents, observations, calculations = domain_evidence(bundles)
    state = InvestigationState(investigation_id='PAIR', anomaly=AnomalyEvent(anomaly_id='A', ticker='AAA', related_entities=('BBB',),
        detected_at=D, anomaly_type='pair', summary='Historical pair deviation'), fundamentals=bundles,
        documents=documents, observations=observations, calculations=calculations)
    graph = build_investigation_graph(state)
    assert {n.kind.value for n in graph.nodes} >= {'observation','calculation','document','source'}
    ids = {n.node_id for n in graph.nodes}
    assert all(e.source in ids and e.target in ids for e in graph.edges)
    assert any(e.kind.value == 'calculated_from' and e.target.startswith('calculation:') for e in graph.edges)
    assert all(n.data['metadata']['concept'] != 'roic' for n in graph.nodes if n.kind.value == 'observation')
    assert all(f.available_at <= D for b in graph.fundamentals for f in b.facts)
    assert {f.fact_id for b in bundles for f in b.facts} == {o.observation_id for o in observations}
    assert {r.calculation_id for b in bundles for r in b.calculations if r.status == 'available'} == {c.calculation_id for c in calculations}
    monkeypatch.setattr('urllib.request.urlopen', Mock(side_effect=AssertionError('No network on replay')))
    replay = InvestigationGraph.model_validate_json(graph.model_dump_json())
    assert replay == graph
    context = model_context(bundles)
    assert 'not causal' in context and calculations[0].calculation_id in context


def test_unavailable_pair_keeps_status_without_network(monkeypatch):
    monkeypatch.delenv('SEC_USER_AGENT', raising=False)
    bundles = load_pair(('AAA','BBB'), D)
    assert all(b.status == 'unavailable' and b.warnings for b in bundles)


def test_allowlist_and_context_compatibility(response):
    facts = facts_at(response)
    with pytest.raises(ValueError, match='Unknown metrics'):
        calculate(facts, (END,), ticker='AAA', metrics=('exec_python',))
    facts = tuple(f.model_copy(update={'period_start':date(2022,1,2)}) if f.concept == 'revenue' else f for f in facts)
    assert calculate(facts, (END,), ticker='AAA', metrics=('operating_margin',))[0].status == 'unavailable'


def test_all_public_metrics_missing_data_are_structured():
    results = calculate((), (END,), ticker='AAA', metrics=PUBLIC_METRICS)
    assert len(results) == len(PUBLIC_METRICS)
    assert all(r.status == 'unavailable' and r.value is None and r.unavailable_reason for r in results)


def test_real_investigation_pipeline_uses_both_companies_before_research(response, monkeypatch):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import investigate_historical_pair as pipeline
    from test_pair_simulation import make_signal
    from financial_assistant.domain import SourceDocument, ExtractedClaim, Hypothesis, ModelRun, ModelOperation
    from financial_assistant.retrieval.models import RetrievalBundle
    observed = datetime(2026, 1, 6, 23, 59, 59, 999999, timezone.utc)
    stages, requested = [], []

    def get(ticker, as_of):
        assert as_of == observed
        requested.append(ticker)
        return response.model_copy(update={'ticker':ticker,'cik':'0000000001' if ticker == 'AAA' else '0000000002'})
    document = SourceDocument(document_id='news', title='A reported development', publisher='Fixture',
        url='https://example.com/news', published_at=D, retrieved_at=D, text='Reported company development.')
    run = ModelRun(run_id='extract', provider='fixture', model='offline', operation=ModelOperation.CLAIM_EXTRACTION,
                   prompt_version='fixture', created_at=observed)
    claim = ExtractedClaim(claim_id='claim', text=document.text, claim_type='reported_fact', document_id='news',
                           source_quote=document.text, model_run_id='extract')
    hypothesis_run = run.model_copy(update={'run_id':'hyp', 'operation':ModelOperation.HYPOTHESIS_GENERATION})
    hypotheses = tuple(Hypothesis(hypothesis_id=f'h{i}', text=f'Possible explanation {i}', model_run_id='hyp') for i in range(2))

    def retrieval(plan, **kwargs):
        assert requested == ['AAA','BBB']
        expansion = kwargs['query_expander'](plan.tasks[0], as_of=observed)
        assert expansion == 'expansion'
        return RetrievalBundle(plan_id=plan.plan_id, as_of=observed)

    def expand(provider, task, *, as_of, financial_context):
        assert 'AAA' in financial_context and 'BBB' in financial_context and 'FIN-' in financial_context
        return 'expansion'

    def generate(event, claims, provider, *, financial_context):
        assert requested == ['AAA','BBB'] and 'roic' in financial_context
        assert 'not causal' in financial_context
        return hypothesis_run, hypotheses

    for name in ('CorpusSearchProvider','CorpusDocumentFetcher','SearxngSearchProvider',
                 'TrafilaturaDocumentFetcher','CompositeSearchProvider','DispatchingDocumentFetcher'):
        monkeypatch.setattr(pipeline, name, Mock())
    monkeypatch.setattr(pipeline, 'execute_research_plan', retrieval)
    monkeypatch.setattr(pipeline, 'expand_research_task', expand)
    monkeypatch.setattr(pipeline, 'select_historical_documents', lambda *a, **kw: (document,))
    monkeypatch.setattr(pipeline, 'extract_document_claims', lambda *a: ((document, run, (claim,), None),))
    monkeypatch.setattr(pipeline, 'generate_hypotheses', generate)
    monkeypatch.setattr(pipeline, 'audit_hypotheses', lambda *a, **kw: (run.model_copy(update={'run_id':'audit'}), ()))
    def assess(claims, hypotheses, provider, **kwargs):
        assert claims and hypotheses
        assert kwargs['observations'] and kwargs['calculations']
        assert all(c.calculation_id for c in kwargs['calculations'])
        return (), ()
    monkeypatch.setattr(pipeline, 'assess_relationships', assess)
    graph, _ = pipeline.investigate_signal(make_signal(), observed_at=observed, provider=object(),
        fundamentals_service=FundamentalsService(Mock(get_company_facts=get)), progress=lambda *args: stages.append(args))
    assert len(graph.fundamentals) == 2
    assert all(f.period_end.year < 2025 for b in graph.fundamentals for f in b.facts)
    assert any(n.kind.value == 'calculation' and n.data['metadata']['metric_id'] == 'roic' for n in graph.nodes)
    assert not any(e.kind.value == 'context_for' and e.source.startswith('calculation:') for e in graph.edges)  # No fabricated judgments when assessor returns none.
    assert stages[-1][0] == 'graph_complete'
    assert 'fundamental_metrics_calculated' in next(s[2] for s in stages if s[0] == 'fundamentals_complete')


def test_ambiguous_contexts_and_missing_prior(response):
    raw = deepcopy(response.facts)
    rows = raw['facts']['us-gaap'][CONCEPTS['revenue'][0]]['units']['USD']
    rows.append(dict(rows[2], val=1234))
    facts, warnings = normalize(response.model_copy(update={'facts':raw}), D)
    assert not any(f.concept == 'revenue' and f.period_end == END for f in facts)
    assert any('ambiguous' in w for w in warnings)
    facts = tuple(f for f in facts_at(response) if f.period_end == END)
    for metric in ('roic','asset_turnover','revenue_growth_yoy','share_dilution_yoy'):
        assert calculate(facts, (END,), ticker='AAA', metrics=(metric,))[0].status == 'unavailable'


def test_trends_are_calculations_with_endpoint_lineage(response):
    service = FundamentalsService(Mock(get_company_facts=Mock(return_value=response)))
    bundle = service.calculate_metrics('AAA', D, periods=3)
    changes = [r for r in bundle.calculations if r.metric_id.endswith('_trend')]
    assert changes
    for trend in changes:
        assert trend.formula_version == 'endpoint-trend-v1'
        assert len(trend.input_ids) == 2 and trend.input_fact_ids and 'not a causal' in trend.warnings[0]


def test_calculation_cycles_and_unknown_inputs_are_rejected(response):
    bundles = load_pair(('AAA',), D, service=FundamentalsService(Mock(get_company_facts=Mock(return_value=response))))
    docs, obs, calcs = domain_evidence(bundles)
    anomaly = AnomalyEvent(anomaly_id='A', ticker='AAA', detected_at=D, anomaly_type='pair', summary='Deviation')
    for identifier, message in ((calcs[0].calculation_id,'cycle'), ('unknown','Unknown')):
        bad = calcs[0].model_copy(update={'input_calculation_ids':(identifier,)})
        state = InvestigationState(investigation_id='I', anomaly=anomaly, documents=docs, observations=obs, calculations=(bad,*calcs[1:]))
        with pytest.raises(ValueError, match=message):
            build_investigation_graph(state)


def test_reported_standard_debt_and_nonzero_leases(response):
    raw = deepcopy(response.facts)
    template = raw['facts']['us-gaap']['CashAndCashEquivalentsAtCarryingValue']['units']['USD'][2]
    raw['facts']['us-gaap']['DebtAndCapitalLeaseObligations'] = {'units':{'USD':[dict(template,val=410)]}}
    facts = facts_at(response.model_copy(update={'facts':raw}))
    total = find(facts, 'total_debt')
    assert total.tag == 'DebtAndCapitalLeaseObligations'
    result = calculate(facts, (END,), ticker='AAA', metrics=('net_debt',))[0]
    assert result.value == 310 and any('finance/capital leases' in w for w in result.warnings)
    facts = tuple(f.model_copy(update={'value':10}) if f.concept in ('finance_lease_current','finance_lease_noncurrent') else f for f in facts_at(response))
    assert calculate(facts, (END,), ticker='AAA', metrics=('net_debt',))[0].value == 220


def test_missing_fundamentals_visible_in_graph(monkeypatch):
    monkeypatch.delenv('SEC_USER_AGENT', raising=False)
    state = InvestigationState(investigation_id='I',
        anomaly=AnomalyEvent(anomaly_id='A', ticker='AAA', detected_at=D, anomaly_type='pair', summary='Deviation'),
        fundamentals=load_pair(('AAA','BBB'), D))
    graph = build_investigation_graph(state)
    gaps = [n for n in graph.nodes if n.kind.value == 'missing_evidence']
    assert len(gaps) == 2 and all(n.data['warnings'] for n in gaps)


def test_invalid_requests_fail_before_provider_access():
    provider = Mock()
    service = FundamentalsService(provider)
    with pytest.raises(ValueError):
        service.calculate_metrics('AAA', D, metrics=('not-allowed',))
    with pytest.raises(ValueError):
        service.get_statement_history('AAA', datetime(2024,1,1))
    with pytest.raises(ValueError):
        service.get_statement_history('AAA', D, periods=100)
    with pytest.raises(ValueError):
        service.get_statement_history('AAA', D, frequency='guessed')
    provider.get_company_facts.assert_not_called()
