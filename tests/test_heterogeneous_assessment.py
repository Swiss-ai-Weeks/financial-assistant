"""Offline contract tests, not claims about a live model's classification quality."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from unittest.mock import Mock
import pytest

from financial_assistant.domain import ArgumentNodeKind, RelationKind
from financial_assistant.llm.evidence_arguments import evidence_argument, select_arguments, relationship_diagnostics
from financial_assistant.llm.relation_assessment import assess_relationships, SYSTEM_PROMPT, PROMPT_VERSION
from financial_assistant.claimgraph.builder_v2 import build_investigation_graph
from financial_assistant.fundamentals.service import FundamentalsService, domain_evidence
from test_builder_v2 import make_state
from test_quarterly_fundamentals import fixture, CUTOFF


class ContractProvider:
    provider_name = 'offline-contract'
    model_name = 'fixture'
    def __init__(self, relation='context_for'):
        self.relation = relation
        self.calls = []
    def complete_json(self, *, system, user, reasoning):
        arguments = json.loads(user.split('ANALYTICAL EVIDENCE:\n')[1].split('\nHYPOTHESIS ID:')[0])
        hypothesis = user.split('HYPOTHESIS ID: ')[1].split('\n')[0]
        self.calls.append((arguments, hypothesis, system))
        return {'assessments': [dict(source_kind=a['source_kind'], source_id=a['source_id'],
            hypothesis_id=hypothesis, relation=self.relation, rationale='Offline protocol response; no live model judgment.',
            missing_information=['Market reaction is not observed.']) for a in arguments]}


def arguments():
    state = make_state()
    return (state.claims[0], state.observations[0], state.calculations[0], state.inferences[0])


@pytest.mark.parametrize('item,kind,id', zip(arguments(), ['claim', 'observation', 'calculation', 'inference'], ['C1', 'O1', 'CALC1', 'I1']))
def test_native_identity_and_assessment(item, kind, id):
    adapted = evidence_argument(item)
    assert adapted.source_kind.value == kind and adapted.source_id == id
    runs, assessed = assess_relationships((item,), make_state().hypotheses, ContractProvider())
    assert assessed[0].source_kind.value == kind and assessed[0].source_id == id
    assert runs[0].prompt_version == PROMPT_VERSION == 'relation-assessment-v2'
    if kind == 'inference':
        assert 'NOT a direct observation' in adapted.provenance_summary['method']
        assert adapted.provenance_summary['derived_from_ids'] == ('CALC1',)


@pytest.mark.parametrize('relation', ['supports', 'weakens', 'contradicts', 'context_for', 'unrelated'])
def test_builder_native_edges_and_unrelated_execution_retention(relation):
    state = make_state()
    runs, assessments = assess_relationships(arguments(), state.hypotheses, ContractProvider(relation))
    graph = build_investigation_graph(state.model_copy(update={
        'model_runs': (*state.model_runs, *runs), 'relationship_assessments':assessments}))
    relations = [e for e in graph.edges if e.data.get('model_run_id') == runs[0].run_id]
    assert len(relations) == (0 if relation == 'unrelated' else 4)
    if relations:
        assert {e.source.split(':')[0] for e in relations} == {'claim', 'observation', 'calculation', 'inference'}
        assert all(e.kind.value == relation for e in relations)
    run_node = next(n for n in graph.nodes if n.data.get('run_id') == runs[0].run_id)
    assert len(run_node.data['assessments']) == 4
    assert run_node.data['relationship_diagnostics']['counts'][relation] == 4
    assert any(e.source == 'inference:I1' and e.target == 'calculation:CALC1' and e.kind.value == 'derived_from' for e in graph.edges)


def test_typed_pair_validation_and_execution_identity():
    state = make_state()
    calculation = state.calculations[0]
    provider = ContractProvider()
    _, first = assess_relationships((calculation,), state.hypotheses, provider)
    _, second = assess_relationships((calculation,), state.hypotheses, provider)
    assert first[0].assessment_id != second[0].assessment_id
    invalid = Mock(provider_name='fake', model_name='fake')
    invalid.complete_json.return_value = {'assessments':[dict(source_kind='claim', source_id=calculation.calculation_id,
        hypothesis_id='H1', relation='supports', rationale='Wrong native kind')]}
    with pytest.raises(ValueError, match='do not match'):
        assess_relationships((calculation,), state.hypotheses, invalid)


def test_bounded_selection_prefers_relevant_recent_summaries_and_keeps_inference():
    state = make_state()
    calcs = tuple(state.calculations[0].model_copy(update={'calculation_id':f'C{i}', 'label':'Revenue growth',
        'metadata':{'period_end':f'{2000+i}-12-31', 'frequency':'quarterly', 'metric_id':'revenue_yoy_growth'}}) for i in range(30))
    hypothesis = state.hypotheses[0].model_copy(update={'text':'Revenue growth declined'})
    selected = select_arguments((*state.claims, *calcs, *state.observations, *state.inferences), hypothesis)
    assert len(selected) == 16
    assert sum(a.source_kind == ArgumentNodeKind.INFERENCE for a in selected) == 1
    chosen = [a.source_id for a in selected if a.source_kind == ArgumentNodeKind.CALCULATION]
    assert chosen[0] == 'C29' and 'C0' not in chosen
    with pytest.raises(ValueError): select_arguments(calcs, hypothesis, 21)
    with pytest.raises(ValueError, match='Duplicate'): select_arguments((*calcs, calcs[0]), hypothesis)


def test_descriptive_vs_causal_contract_and_prompt():
    state = make_state()
    narrow = state.hypotheses[0].model_copy(update={'hypothesis_id':'N', 'text':'Revenue growth declined'})
    causal = state.hypotheses[0].model_copy(update={'hypothesis_id':'C', 'text':'Revenue decline caused stock-price divergence'})
    class SemanticExample(ContractProvider):
        def complete_json(self, **kwargs):
            # Explicit protocol example, not a heuristic installed in production.
            self.relation = 'context_for' if 'HYPOTHESIS ID: C\n' in kwargs['user'] else 'supports'
            return super().complete_json(**kwargs)
    _, assessed = assess_relationships(state.calculations, (narrow, causal), SemanticExample())
    assert [a.relation for a in assessed] == [RelationKind.SUPPORTS, RelationKind.CONTEXT_FOR]
    assert all(a.missing_information for a in assessed)
    assert 'does NOT automatically support' in SYSTEM_PROMPT
    assert 'decreases plausibility without conflicting' in SYSTEM_PROMPT
    assert 'conflicts with something required' in SYSTEM_PROMPT
    assert 'Do not require balanced counts' in SYSTEM_PROMPT


def industrial_bundle():
    return FundamentalsService(Mock(get_company_facts=Mock(return_value=fixture()))).quarterly_metrics('AAA', CUTOFF)


def test_actual_sec_calculation_lineage_survives_assessment():
    bundle = industrial_bundle()
    docs, obs, calcs = domain_evidence((bundle,))
    state = make_state()
    metric = next(c for c in calcs if c.metadata['metric_id'] == 'revenue_yoy_growth')
    runs, assessed = assess_relationships((), state.hypotheses, ContractProvider('supports'), calculations=(metric,))
    graph = build_investigation_graph(state.model_copy(update={'documents':(*state.documents, *docs),
        'observations':obs, 'calculations':calcs, 'inferences':(), 'model_runs':(*state.model_runs, *runs),
        'relationship_assessments':assessed}))
    edges = {(e.source,e.target,e.kind.value) for e in graph.edges}
    assert (f'calculation:{metric.calculation_id}', 'hypothesis:H1', 'supports') in edges
    visited = set()
    def visit(id):
        if id in visited: return
        visited.add(id)
        for source,target,kind in edges:
            if source == id and kind in ('calculated_from', 'extracted_from'): visit(target)
    visit('calculation:' + metric.calculation_id)
    assert any(id.startswith('observation:SEC-') for id in visited)
    assert any(id.startswith('document:SEC-FILING-') for id in visited)
    assert not any(e.source == 'calculation:' + metric.calculation_id and e.kind.value == 'context_for' for e in graph.edges)


def test_followup_reassesses_new_sec_without_documentary_claims(monkeypatch):
    import missing_evidence_followup as f
    from financial_assistant.retrieval.models import RetrievalBundle
    state = make_state()
    original = build_investigation_graph(state).model_dump(mode='json')
    unrelated = state.hypotheses[0].model_copy(update={'hypothesis_id':'H2'})
    original['nodes'].append(dict(node_id='hypothesis:H2', kind='hypothesis', label=unrelated.text, data=unrelated.model_dump(mode='json')))
    monkeypatch.setattr(f, 'load_pair', lambda *a, **k: (industrial_bundle(),))
    monkeypatch.setattr(f, 'execute_research_plan', lambda plan, **kw: RetrievalBundle(plan_id=plan.plan_id, as_of=plan.as_of))
    monkeypatch.setattr(f, 'extract_document_claims', lambda *a: ())
    provider = ContractProvider()
    result = f.run_followup(original, 'evidence_requirement:ER1', provider, 'HET', lambda *a, **k: None, peer_rows=[])
    assert len(provider.calls) == 1 and provider.calls[0][1] == 'H1'
    assert len(provider.calls[0][0]) <= 16
    assert any(a['source_kind'] == 'calculation' for a in provider.calls[0][0])
    assert all(e in result['edges'] for e in original['edges'])
    assert result['followups'][0]['resolution']['status'] == 'unresolved'  # No fake resolution from relation counts.
    assert len([n for n in result['nodes'] if n['kind'] == 'research_task']) == 4
    # Re-running with the now-existing SEC evidence does not reassess those same nodes.
    provider.calls.clear()
    f.run_followup(result, 'evidence_requirement:ER1', provider, 'HET2', lambda *a, **k: None, peer_rows=[])
    assert not provider.calls


def test_diagnostics_are_counts_not_requirements():
    _, assessments = assess_relationships(arguments(), make_state().hypotheses, ContractProvider('unrelated'))
    diagnostics = relationship_diagnostics(assessments)
    assert diagnostics['counts']['supports'] == 0
    assert diagnostics['counts']['unrelated'] == 4
    assert all(row['unrelated'] == 1 for row in diagnostics['by_source_kind'].values())
