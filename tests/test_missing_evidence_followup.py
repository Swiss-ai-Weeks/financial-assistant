"""Bounded follow-up contracts; all retrieval/model responses are deterministic fixtures."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import missing_evidence_followup as f
from financial_assistant.domain import RelationKind
from test_builder_v2 import make_state, NOW
from financial_assistant.claimgraph.builder_v2 import build_investigation_graph
from financial_assistant.retrieval.models import RetrievalBundle


def graph():
    return build_investigation_graph(make_state()).model_dump(mode='json')


def test_peer_selection_is_bounded_dated_and_constrained():
    base = dict(mapping_status='mapped', universe='u', currency='USD', sector='Banks', industry='Community', valid_from='2020-01-01')
    rows = [dict(base, yahoo_ticker=t) for t in ['T', 'C', 'D', 'B', 'A', 'E']]
    rows += [dict(base, yahoo_ticker='BAD', currency='EUR'), dict(base, yahoo_ticker='FUTURE', valid_from='2030-01-01'),
             dict(base, yahoo_ticker='WRONG', industry='Insurance')]
    assert f.peer_context(('T', 'C'), NOW, rows)['peers'] == ['A', 'B', 'D']
    assert f.peer_context(('T',), NOW, [dict(base, yahoo_ticker='T', valid_from='')])['status'] == 'unavailable'


def test_plan_bound_and_contradictory_scope():
    plan = f.plan_followup('run', make_state().anomaly, 'Why?', NOW, {'peers': ['A'], 'sector': 'Banks'})
    assert len(plan.tasks) == 4
    assert plan.as_of == NOW
    assert 'Contradictory' in plan.tasks[-1].question


@pytest.mark.parametrize('status', ['unresolved', 'partially_answered', 'answered'])
def test_resolution_references_actual_evidence_and_retains_counterpoints(status):
    provider = Mock()
    provider.complete_json.return_value = dict(status=status, summary='Result', supporting_item_ids=['C'], contradicting_item_ids=['X'])
    result = f.assess_resolution(provider, 'Why?', [{'node_id':'C'}, {'node_id':'X'}])
    assert result.status == status and result.contradicting_item_ids == ['X']
    provider.complete_json.return_value['supporting_item_ids'] = ['invented']
    with pytest.raises(ValueError):
        f.assess_resolution(provider, 'Why?', [{'node_id':'C'}, {'node_id':'X'}])


def test_no_evidence_never_calls_resolution_model():
    provider = Mock()
    assert f.assess_resolution(provider, 'Why?', []).status == 'unresolved'
    provider.complete_json.assert_not_called()


@pytest.fixture
def empty_cycle(monkeypatch):
    load = Mock(return_value=())
    retrieve = Mock(side_effect=lambda plan, **kw: RetrievalBundle(plan_id=plan.plan_id, as_of=plan.as_of))
    monkeypatch.setattr(f, 'load_pair', load)
    monkeypatch.setattr(f, 'execute_research_plan', retrieve)
    monkeypatch.setattr(f, 'extract_document_claims', Mock(return_value=()))
    reassess = Mock()
    monkeypatch.setattr(f, 'assess_relationships', reassess)
    return load, retrieve, reassess


def test_explicit_cycle_merges_preserves_and_does_not_recurse(empty_cycle):
    original = graph()
    before = json.dumps(original)
    gap = next(n for n in original['nodes'] if n['kind'] == 'evidence_requirement')
    stages = []
    provider = Mock(provider_name='test', model_name='test')
    result = f.run_followup(original, gap['node_id'], provider, 'RUN', lambda stage, **kw: stages.append(stage), peer_rows=[])
    assert json.dumps(original) == before
    assert len(result['nodes']) > len(original['nodes'])
    assert result['investigation_id'] == original['investigation_id']
    assert set(n['node_id'] for n in original['nodes']) <= set(n['node_id'] for n in result['nodes'])
    assert all(e in result['edges'] for e in original['edges'])
    updated = next(n for n in result['nodes'] if n['node_id'] == gap['node_id'])
    assert updated['data']['resolution_status'] == 'unresolved'
    assert len(updated['data']['followup_history']) == 1
    assert json.loads(json.dumps(result))['followups'] == result['followups']
    empty_cycle[1].assert_called_once()
    assert empty_cycle[0].call_args.args[1] == make_state().anomaly.detected_at
    empty_cycle[2].assert_not_called()
    assert 'resolution_assessment' in stages and 'graph_complete' in stages
    for old in original['nodes']:
        if old['node_id'] != gap['node_id']:
            assert old in result['nodes']


def test_provider_failure_isolated_without_exception_body():
    records = []
    provider = Mock(name='provider')
    provider.name = 'bookreader'
    provider.search.side_effect = RuntimeError('secret token and document body')
    assert f.RecordedSearch(provider, records).search('query', task_id='task') == ()
    assert records[0]['status'] == 'failed'
    assert 'secret' not in json.dumps(records)


def test_api_lock_and_failure_preserve_graph(monkeypatch, tmp_path, empty_cycle):
    import investigation_api as api
    monkeypatch.chdir(tmp_path)
    original = graph()
    request = dict(graph=original, requirement_id='evidence_requirement:ER1', **api.public_models()['models'][0])
    f.FOLLOWUP_LOCK.acquire()
    try:
        with pytest.raises(ValueError, match='One follow-up'):
            api.investigate_missing_evidence(request)
    finally:
        f.FOLLOWUP_LOCK.release()
    result = api.investigate_missing_evidence(request)
    replay = json.loads((tmp_path / '.run/replays' / f"{result['replay_id']}.json").read_text())
    assert replay['followups'] == result['followups']
    assert len(original['nodes']) < len(result['nodes'])


def test_grounded_contradiction_targeted_reassessment_and_future_exclusion(monkeypatch):
    from datetime import timedelta
    state = make_state()
    original = graph()
    # Add an unrelated hypothesis which must never reach reassessment.
    unrelated = state.hypotheses[0].model_copy(update={'hypothesis_id':'H2'})
    original['nodes'].append(dict(node_id='hypothesis:H2', kind='hypothesis', label=unrelated.text, data=unrelated.model_dump(mode='json')))
    doc = state.documents[0].model_copy(update={'document_id':'NEW', 'published_at':NOW - timedelta(days=1)})
    future = doc.model_copy(update={'document_id':'FUTURE', 'published_at':NOW + timedelta(days=1)})
    claim = state.claims[0].model_copy(update={'claim_id':'NEW-C', 'document_id':'NEW'})
    extraction = next(r for r in state.model_runs if r.run_id == claim.model_run_id)
    relation = state.relationship_assessments[0].model_copy(update={'source_id':'NEW-C', 'relation':RelationKind.CONTRADICTS})
    relation_run = next(r for r in state.model_runs if r.run_id == relation.model_run_id)
    monkeypatch.setattr(f, 'load_pair', Mock(return_value=()))
    monkeypatch.setattr(f, 'execute_research_plan', lambda plan, **kw: RetrievalBundle(plan_id=plan.plan_id, as_of=plan.as_of, documents=(doc, future)))
    extract = Mock(return_value=((doc, extraction, (claim,), None),))
    monkeypatch.setattr(f, 'extract_document_claims', extract)
    assess = Mock(return_value=((relation_run,), (relation,)))
    monkeypatch.setattr(f, 'assess_relationships', assess)
    provider = Mock(provider_name='test', model_name='test')
    provider.complete_json.return_value = dict(status='partially_answered', summary='Counter-evidence found',
        supporting_item_ids=[], contradicting_item_ids=['claim:NEW-C'], remaining_question='What other mechanism?')
    result = f.run_followup(original, 'evidence_requirement:ER1', provider, 'R', lambda *a, **k: None, peer_rows=[])
    assert [d.document_id for d in extract.call_args.args[0]] == ['NEW']
    assert [h.hypothesis_id for h in assess.call_args.args[1]] == ['H1']
    assert any(e['kind'] == 'contradicts' and e['source'] == 'claim:NEW-C' for e in result['edges'])
    assert not any(n['node_id'] == 'document:FUTURE' for n in result['nodes'])
    assert any(n['label'] == 'What other mechanism?' and n['kind'] == 'missing_evidence' for n in result['nodes'])
    assert result['followups'][0]['resolution']['status'] == 'partially_answered'
    assert 'text' not in next(n['data'] for n in result['nodes'] if n['node_id'] == 'document:NEW')


def test_failed_reassessment_preserves_old_relationships(monkeypatch, empty_cycle):
    state = make_state()
    doc = state.documents[0].model_copy(update={'document_id':'NEW'})
    claim = state.claims[0].model_copy(update={'claim_id':'NEW-C', 'document_id':'NEW'})
    run = next(r for r in state.model_runs if r.run_id == claim.model_run_id)
    monkeypatch.setattr(f, 'extract_document_claims', Mock(return_value=((doc, run, (claim,), None),)))
    monkeypatch.setattr(f, 'execute_research_plan', lambda plan, **kw: RetrievalBundle(plan_id=plan.plan_id, as_of=plan.as_of, documents=(doc,)))
    empty_cycle[2].side_effect = RuntimeError('secret')
    provider = Mock(provider_name='test', model_name='test')
    provider.complete_json.side_effect = RuntimeError('secret')
    original = graph()
    result = f.run_followup(original, 'evidence_requirement:ER1', provider, 'FAIL', lambda *a, **k: None, peer_rows=[])
    assert all(e in result['edges'] for e in original['edges'])
    assert 'secret' not in json.dumps(result)
    action = next(n for n in result['nodes'] if n['kind'] == 'agent_action')
    assert any(e['stage'] == 'relationship_assessment' for e in action['data']['failures'])


def test_all_sources_contribute_and_progress_is_sanitized(monkeypatch):
    from financial_assistant.retrieval.models import SearchHit
    from financial_assistant.domain import Observation, Calculation
    from investigation_progress import ProgressRegistry
    from datetime import timedelta
    state = make_state()
    source_docs = {}
    class Search:
        def __init__(self, name): self.name = name
        def search(self, query, *, task_id, limit, as_of):
            assert as_of == NOW
            id = f'{self.name}-{task_id}'
            source_docs[id] = state.documents[0].model_copy(update={'document_id':id,
                'published_at':NOW - timedelta(days=1), 'publisher':self.name})
            return (SearchHit(hit_id=id, task_id=task_id, provider=self.name, query=query, rank=1,
                title=id, url=f'https://example.com/{id}', published_at=NOW - timedelta(days=1)),)
    class Fetch:
        def fetch(self, hit, *, retrieved_at): return source_docs[hit.hit_id]
    class Provider:
        provider_name = 'test'
        model_name = 'test'
        def complete_json(self, **kw): raise ValueError('sensitive transport error')
    monkeypatch.setattr(f, 'load_pair', Mock(return_value=()))
    filing = state.documents[1].model_copy(update={'document_id':'SEC-NEW'})
    obs = Observation(observation_id='SEC-O', name='Revenue', value=10, unit='USD', source_document_id='SEC-NEW')
    calc = Calculation(calculation_id='SEC-C', label='Revenue growth', expression='a/b-1', value=.1, unit='ratio', input_observation_ids=('SEC-O',))
    monkeypatch.setattr(f, 'domain_evidence', lambda bundles: ((filing,), (obs,), (calc,)))
    monkeypatch.setattr(f, 'extract_document_claims', lambda documents, provider: ())
    registry = ProgressRegistry()
    registry.start('ALL')
    def report(stage, **kw): registry.report('ALL', stage, message='secret', metrics={**kw.get('metrics', {}), 'body':'private'})
    result = f.run_followup(graph(), 'evidence_requirement:ER1', Provider(), 'ALL', report,
        search_providers=(Search('bookreader'), Search('searxng')), fetcher=Fetch(), peer_rows=[])
    assert any(n['node_id'] == 'observation:SEC-O' for n in result['nodes'])
    assert any(n['node_id'] == 'calculation:SEC-C' for n in result['nodes'])
    publishers = {n['data'].get('publisher') for n in result['nodes'] if n['kind'] == 'document'}
    assert {'bookreader', 'searxng'} <= publishers
    assert not any(word in json.dumps(registry.get('ALL')) for word in ('secret', 'private', 'sensitive'))
    assert 'sensitive' not in json.dumps(result)
    ids = {n['node_id'] for n in result['nodes']}
    assert all(e['source'] in ids and e['target'] in ids for e in result['edges'])


def test_two_turn_deltas_preserve_prior_history(empty_cycle):
    original = graph()
    requirement = next(n['node_id'] for n in original['nodes'] if n['kind'] == 'evidence_requirement')
    provider = Mock(provider_name='test', model_name='test')
    first = f.run_followup(original, requirement, provider, 'TURN1', lambda *a, **kw: None, peer_rows=[])
    second = f.run_followup(first, requirement, provider, 'TURN2', lambda *a, **kw: None, peer_rows=[])
    assert second['followups'][0] == first['followups'][0]
    delta = second['followups'][-1]['delta']
    assert set(delta['added_node_ids']) == {n['node_id'] for n in second['nodes']} - {n['node_id'] for n in first['nodes']}
    assert set(delta['added_edge_ids']) == {e['edge_id'] for e in second['edges']} - {e['edge_id'] for e in first['edges']}
    assert not set(delta['added_node_ids']) & set(first['followups'][0]['delta']['added_node_ids'])
    assert delta['previous_resolution'] == delta['new_resolution'] == 'unresolved'
