"""One human-triggered, bounded research cycle. No scheduling or recursion."""
import csv
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import BaseModel, ConfigDict
from financial_assistant.claimgraph.builder_v2 import build_investigation_graph
from financial_assistant.domain import AnomalyEvent, Hypothesis, InvestigationState, ModelRun
from financial_assistant.fundamentals.service import load_pair, model_context, domain_evidence
from financial_assistant.llm import assess_relationships
from financial_assistant.llm.evidence_arguments import relationship_diagnostics
from financial_assistant.research.identity import resolve_entities
from financial_assistant.research.models import ResearchPlan, ResearchTask
from financial_assistant.retrieval import (CorpusSearchProvider, CorpusDocumentFetcher,
    SearxngSearchProvider, TrafilaturaDocumentFetcher, execute_research_plan)
from financial_assistant.retrieval.composite import CompositeSearchProvider, DispatchingDocumentFetcher
from financial_assistant.retrieval.query_expansion import expand_research_task, QueryExpansion, ExpandedQuery
from investigate_historical_pair import select_historical_documents, extract_document_claims, parse_aware_datetime

FOLLOWUP_LOCK = Lock()


def peer_context(tickers, cutoff, rows=None):
    if rows is None:
        with (Path(__file__).resolve().parents[1] / 'data/universe/global_equities.csv').open() as stream:
            rows = list(csv.DictReader(stream))
    # Undated current membership must not masquerade as historical peer identity.
    eligible = [r for r in rows if r.get('mapping_status') == 'mapped'
                and r.get('valid_from') and r['valid_from'] <= cutoff.date().isoformat()
                and (not r.get('valid_to') or cutoff.date().isoformat() < r['valid_to'])]
    target = next((r for r in eligible if r['yahoo_ticker'] == tickers[0]), None)
    if not target:
        return {'peers': [], 'sector': None, 'status': 'unavailable',
                'reason': 'No point-in-time universe classification; current metadata is not historical evidence.'}
    keys = ['universe', 'currency', 'sector'] + [k for k in ('industry', 'subindustry') if target.get(k)]
    peers = sorted({r['yahoo_ticker'] for r in eligible if r['yahoo_ticker'] not in tickers
                    and all(target.get(k) and r.get(k) == target[k] for k in keys)})[:3]
    return {'peers': peers, 'sector': target['sector'], 'status': 'available',
            'criteria': keys, 'identity_valid_from': target['valid_from']}


def plan_followup(run_id, anomaly, question, cutoff, peers):
    entities = resolve_entities((anomaly.ticker, *anomaly.related_entities, *peers['peers']))
    purposes = [('primary_disclosures', 'Company-specific evidence'),
                ('shared_context', 'Peer comparison; normal versus disproportionate exposure'),
                ('shared_context', 'Sector context; context and analogy are not causal proof'),
                ('recent_news', 'Contradictory evidence and alternative explanations; permit insufficient evidence')]
    return ResearchPlan(plan_id=run_id, anomaly_id=anomaly.anomaly_id, as_of=cutoff,
        tasks=tuple(ResearchTask(task_id=f'{run_id}-task-{i}', kind=kind, entities=entities,
            question=f'{question}\nResearch scope: {purpose}. Sector: {peers.get("sector") or "unverified"}.',
            rationale='Resolve the selected evidence requirement without presuming its explanation is true.',
            source_preferences=('sec_edgar', 'news', 'market_context'), lookback_days=45, priority=i)
            for i, (kind, purpose) in enumerate(purposes, 1)))


class Resolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['unresolved', 'partially_answered', 'answered']
    summary: str
    supporting_item_ids: list[str] = []
    contradicting_item_ids: list[str] = []
    remaining_question: str = ''


def assess_resolution(provider, question, items):
    if not items:
        return Resolution(status='unresolved', summary='No new grounded evidence addresses the question.', remaining_question=question)
    result = Resolution.model_validate(provider.complete_json(system='''Assess this missing-evidence question using only the supplied new evidence.
Return JSON: status (answered, partially_answered, unresolved), summary, supporting_item_ids,
contradicting_item_ids, remaining_question. IDs must be supplied node IDs. Retain contradictory evidence.
Answered requires evidence that actually resolves the question, including a well-grounded negative answer.
Retrieval alone is not an answer. Peer behavior is context/analogy, never causal proof.
Partial evidence leaves partially_answered; no relevant evidence leaves unresolved.
Do not invent metrics or causal mechanisms.''', user=json.dumps({'question': question, 'evidence': items}), reasoning=False))
    ids = {n['node_id'] for n in items}
    cited = set(result.supporting_item_ids + result.contradicting_item_ids)
    if not cited <= ids or (result.status != 'unresolved' and not cited):
        raise ValueError('Resolution requires valid new evidence references')
    if result.status != 'answered' and not result.remaining_question:
        result.remaining_question = question
    return result


class LazyAdapter:
    """Configuration errors belong to the affected source, not the entire cycle."""
    def __init__(self, name, factory):
        self.name, self.factory = name, factory
        self.instance = None

    def search(self, *args, **kwargs):
        self.instance = self.instance or self.factory()
        return self.instance.search(*args, **kwargs)

    def fetch(self, *args, **kwargs):
        self.instance = self.instance or self.factory()
        return self.instance.fetch(*args, **kwargs)


class RecordedSearch:
    """Isolate failures per provider; expose only fixed status metadata."""
    def __init__(self, provider, records):
        self.provider, self.records, self.name = provider, records, provider.name

    def search(self, query, **kwargs):
        entry = {'provider': self.name, 'task_id': kwargs['task_id'], 'query': query,
                 'retrieved_at': datetime.now(timezone.utc).isoformat()}
        try:
            hits = self.provider.search(query, **kwargs)
            entry.update(status='complete', hits=len(hits))
            return hits
        except Exception:
            entry.update(status='failed', reason='Search provider unavailable')
            return ()
        finally:
            self.records.append(entry)


def run_followup(graph, requirement_id, provider, run_id, report, *, fundamentals_service=None,
                 search_providers=None, fetcher=None, peer_rows=None):
    original = deepcopy(graph)
    selected = next((n for n in graph['nodes'] if n['node_id'] == requirement_id), None)
    if not selected or selected['kind'] not in ('missing_evidence', 'evidence_requirement'):
        raise ValueError('Select a Missing Evidence or Evidence Requirement node')
    anomaly = AnomalyEvent.model_validate(next(n['data'] for n in graph['nodes'] if n['kind'] == 'anomaly'))
    cutoff = parse_aware_datetime(anomaly.metadata.get('observed_at', anomaly.detected_at.isoformat()))
    parent_ids = {e['source'] for e in graph['edges'] if e['target'] == requirement_id and e['kind'] == 'requires'}
    if selected['data'].get('hypothesis_id'):
        parent_ids.add('hypothesis:' + selected['data']['hypothesis_id'])
    # A requirement attached to a claim may affect only hypotheses directly linked to that claim.
    parent_ids |= {e['target'] for e in graph['edges'] if e['source'] in parent_ids
                   and e['kind'] in ('supports', 'weakens', 'contradicts', 'context_for')}
    hypotheses = tuple(Hypothesis.model_validate(n['data']) for n in graph['nodes']
                       if n['node_id'] in parent_ids and n['kind'] == 'hypothesis')
    question = selected['label']
    tickers = (anomaly.ticker, *anomaly.related_entities)
    report('followup_preparing')
    peers = peer_context(tickers, cutoff, peer_rows)
    plan = plan_followup(run_id, anomaly, question, cutoff, peers)
    report('research_plan', metrics={'research_tasks': len(plan.tasks)})
    fundamentals = load_pair((*tickers, *peers['peers']), cutoff, service=fundamentals_service,
                             progress=lambda stage, message='', **kw: report(stage, metrics=kw))
    context = model_context(fundamentals)
    relevant = [n for n in graph['nodes'] if n['node_id'] in parent_ids or
                any(e['target'] in parent_ids and e['source'] == n['node_id'] for e in graph['edges'])]
    planning_context = context + '\nSelected question and existing local evidence:\n' + json.dumps(
        {'question': question, 'parents_and_evidence': relevant, 'peer_identity': peers})
    tool_records, expansions, failures = [], [], []
    def expand(task, *, as_of):
        try:
            expansion = expand_research_task(provider, task, as_of=as_of, financial_context=planning_context)
            expansion = expansion.model_copy(update={'queries': expansion.queries[:3]})
            expansions.append({**expansion.model_dump(mode='json'), 'status': 'complete',
                               'provider': provider.provider_name, 'model': provider.model_name,
                               'created_at': datetime.now(timezone.utc).isoformat()})
            return expansion
        except Exception:
            expansions.append({'task_id': task.task_id, 'status': 'failed', 'provider': provider.provider_name,
                               'model': provider.model_name})
            return QueryExpansion(task_id=task.task_id, queries=(ExpandedQuery(
                text=f'{anomaly.ticker} {question}'[:120], proximity='direct', relation='evidence_requirement',
                reason='Deterministic fallback after expansion failure'),))
    search = CompositeSearchProvider(tuple(RecordedSearch(p, tool_records) for p in
        (search_providers if search_providers is not None else (LazyAdapter('bookreader', lambda: CorpusSearchProvider(lookback_days=45)), LazyAdapter('searxng', SearxngSearchProvider)))))
    fetcher = fetcher or DispatchingDocumentFetcher({'bookreader': LazyAdapter('bookreader', CorpusDocumentFetcher), 'searxng': LazyAdapter('searxng', TrafilaturaDocumentFetcher)})
    report('retrieval')
    bundle = execute_research_plan(plan, search_provider=search, document_fetcher=fetcher,
        retrieved_at=datetime.now(timezone.utc), per_task_limit=2, query_expander=expand)
    report('retrieval_complete', metrics={'retrieval_records': len(bundle.records), 'search_hits': len(bundle.hits)})
    documents = select_historical_documents(bundle, plan, limit=6)
    report('evidence_selection', metrics={'documents_selected': len(documents)})
    report('claim_extraction')
    claims, runs = [], []
    for document, run, extracted, error in extract_document_claims(documents, provider):
        if error:
            failures.append({'stage': 'claim_extraction', 'document_id': document.document_id, 'status': 'failed'})
        else:
            runs.append(run)
            claims.extend(extracted[:2])
    claims = tuple({c.claim_id: c for c in claims}.values())[:12]
    report('claim_extraction_complete', metrics={'claims': len(claims)})
    financial_docs, observations, calculations = domain_evidence(fundamentals)
    base_runs = tuple(ModelRun.model_validate({k: v for k, v in n['data'].items() if k in ModelRun.model_fields}) for n in graph['nodes']
                      if n['kind'] == 'model_run' and n['data'].get('run_id') in {h.model_run_id for h in hypotheses})
    old_ids = {n['node_id'] for n in graph['nodes']}
    new_claims = tuple(c for c in claims if 'claim:' + c.claim_id not in old_ids)
    new_observations = tuple(o for o in observations if 'observation:' + o.observation_id not in old_ids)
    new_calculations = tuple(c for c in calculations if 'calculation:' + c.calculation_id not in old_ids)
    report('relationship_assessment')
    assessments = []
    reassessed_ids = []
    for hypothesis in hypotheses:
        if not (new_claims or new_observations or new_calculations):
            break
        try:
            rr, aa = assess_relationships(new_claims, (hypothesis,), provider,
                observations=new_observations, calculations=new_calculations)
            reassessed_ids.append('hypothesis:' + hypothesis.hypothesis_id)
            runs.extend(rr)
            assessments.extend(a.model_copy(update={'assessment_id': f'{run_id}-{a.assessment_id}'}) for a in aa)
        except Exception:
            failures.append({'stage': 'relationship_assessment', 'hypothesis_id': hypothesis.hypothesis_id, 'status': 'failed'})
    report('relationship_assessment_complete', metrics={'relationships': len(assessments)})
    delta = build_investigation_graph(InvestigationState(investigation_id=graph['investigation_id'], anomaly=anomaly,
        fundamentals=fundamentals, documents=(*documents, *financial_docs), observations=observations,
        calculations=calculations, claims=claims, hypotheses=hypotheses,
        model_runs=(*base_runs, *runs), relationship_assessments=tuple(assessments))).model_dump(mode='json')
    old_ids = {n['node_id'] for n in graph['nodes']}
    new_nodes = [n for n in delta['nodes'] if n['node_id'] not in old_ids]
    evidence = [n for n in new_nodes if n['kind'] in ('claim', 'calculation', 'observation')]
    # Model context remains compact: raw XBRL observations are never supplied to resolution.
    resolution_items = [n for n in evidence if n['kind'] != 'observation']
    report('resolution_assessment')
    resolution_run = f'{run_id}-resolution'
    try:
        resolution = assess_resolution(provider, question, resolution_items)
    except Exception:
        failures.append({'stage': 'resolution_assessment', 'status': 'failed'})
        resolution = Resolution(status='unresolved', summary='Resolution assessment unavailable.', remaining_question=question)
    resolution_data = {**resolution.model_dump(), 'requirement_id': requirement_id, 'model_run_id': resolution_run}
    report('resolution_assessment_complete')
    report('graph_build')
    action_id = f'action:{run_id}'
    def node(id, kind, label, data):
        new_nodes.append(dict(node_id=id, kind=kind, label=label, data=data))
    edges = []
    def edge(source, target, kind, data=None):
        edges.append(dict(edge_id=f'{run_id}-edge-{len(edges)}', source=source, target=target, kind=kind, data=data or {}))
    node(action_id, 'agent_action', 'Human-triggered follow-up research', {
        'run_id': run_id, 'originating_requirement_id': requirement_id, 'human_action': 'Investigate this question',
        'cutoff': cutoff.isoformat(), 'created_at': datetime.now(timezone.utc).isoformat(),
        'provider': provider.provider_name, 'model': provider.model_name, 'peer_context': peers,
        'resolution': resolution_data, 'failures': failures,
        'relationship_diagnostics': relationship_diagnostics(assessments),
        'counts': {'documents': len(documents), 'sec_calculations': len(calculations), 'grounded_claims': len(claims)},
        'sec_status': [{'ticker': b.ticker, 'status': b.status, 'warnings': b.warnings} for b in fundamentals]})
    edge(action_id, requirement_id, 'investigates')
    for i, bundle_item in enumerate(fundamentals):
        sec_id = f'{run_id}-sec-{i}'
        node(sec_id, 'tool_call', f'SEC quarterly fundamentals: {bundle_item.ticker}', {
            'provider': 'SEC EDGAR', 'ticker': bundle_item.ticker, 'status': bundle_item.status,
            'cutoff': cutoff.isoformat(), 'retrieved_at': bundle_item.retrieved_at.isoformat() if bundle_item.retrieved_at else None,
            'warnings': list(bundle_item.warnings), 'operation': 'quarterly snapshots and deterministic trends'})
        edge(action_id, sec_id, 'retrieved')
        for observation in observations:
            if observation.metadata.get('ticker') == bundle_item.ticker:
                edge('observation:' + observation.observation_id, sec_id, 'produced_by')
    for task in plan.tasks:
        node(task.task_id, 'research_task', task.question, task.model_dump(mode='json'))
        edge(action_id, task.task_id, 'generated_task')
    for i, expansion in enumerate(expansions):
        id = f'{run_id}-expansion-{i}'
        node(id, 'model_run', 'Query expansion — research hypotheses, not evidence', expansion)
        edge(expansion['task_id'], id, 'produced_by')
    for i, record in enumerate(tool_records + [r.model_dump(mode='json', exclude={'note'}) for r in bundle.records]):
        id = f'{run_id}-tool-{i}'
        node(id, 'tool_call', f"{record['provider']}: {record['status']}", record)
        edge(record['task_id'], id, 'retrieved')
        doc_id = 'document:' + (record.get('document_id') or '')
        if any(n['node_id'] == doc_id for n in new_nodes):
            edge(id, doc_id, 'retrieved')
    node(resolution_run, 'model_run', 'Missing evidence resolution assessment', {
        'provider': provider.provider_name, 'model': provider.model_name, 'operation': 'resolution_assessment',
        'created_at': datetime.now(timezone.utc).isoformat(), 'resolution': resolution_data,
        'status': 'failed' if any(f['stage'] == 'resolution_assessment' for f in failures) else 'complete' if resolution_items else 'skipped_no_evidence'})
    edge(requirement_id, resolution_run, 'produced_by')
    for id in resolution.supporting_item_ids + resolution.contradicting_item_ids:
        edge(resolution_run, id, 'derived_from')
        if resolution.status != 'unresolved':
            edge(id, requirement_id, 'resolves' if resolution.status == 'answered' else 'partially_resolves')
    if resolution.remaining_question and resolution.remaining_question != question:
        gap = f'{run_id}-remaining'
        node(gap, 'missing_evidence', resolution.remaining_question, {'resolution_status': 'unresolved',
             'hypothesis_id': hypotheses[0].hypothesis_id if hypotheses else None, 'originating_run_id': run_id})
        edge(requirement_id, gap, 'requires')
    for n in list(new_nodes):
        if n['kind'] in ('claim', 'observation', 'calculation', 'document', 'model_run'):
            edge(n['node_id'], action_id, 'produced_by')
    for n in original['nodes']:
        if n['node_id'] == requirement_id:
            n['data'].update(resolution_status=resolution.status, resolution=resolution_data,
                followup_history=[*n['data'].get('followup_history', []), action_id])
    original['nodes'].extend(new_nodes)
    old_edges = {e['edge_id'] for e in original['edges']}
    original['edges'].extend(e for e in delta['edges'] if e['edge_id'] not in old_edges)
    original['edges'].extend(edges)
    # Preserve the original financial snapshot; follow-up bundles are separately recorded.
    original.setdefault('followups', []).append({'run_id': run_id, 'requirement_id': requirement_id,
         'cutoff': cutoff.isoformat(), 'resolution': resolution_data, 'action_id': action_id,
        'delta': {**followup_delta(graph, original, run_id, requirement_id, question, action_id), 'reassessed_hypothesis_ids': reassessed_ids}})
    report('graph_complete', metrics={'nodes': len(original['nodes']), 'edges': len(original['edges'])})
    return original


def followup_delta(before, after, run_id, requirement_id, question, action_id):
    old_nodes = {n['node_id'] for n in before['nodes']}
    old_edges = {e['edge_id'] for e in before['edges']}
    edges = [e for e in after['edges'] if e['edge_id'] not in old_edges]
    previous = next(n for n in before['nodes'] if n['node_id'] == requirement_id)['data']
    current = next(n for n in after['nodes'] if n['node_id'] == requirement_id)['data']
    delta = dict(run_id=run_id, requirement_id=requirement_id, question=question, action_id=action_id,
        added_node_ids=[n['node_id'] for n in after['nodes'] if n['node_id'] not in old_nodes],
        added_edge_ids=[e['edge_id'] for e in edges],
        previous_resolution=previous.get('resolution_status', 'unresolved'),
        new_resolution=current.get('resolution_status', 'unresolved'),
        remaining_question=current.get('resolution', {}).get('remaining_question'))
    for name, kind in [('supporting', 'supports'), ('weakening', 'weakens'), ('contradicting', 'contradicts'), ('context', 'context_for')]:
        delta[f'new_{name}_ids'] = [e['edge_id'] for e in edges if e['kind'] == kind]
    hypotheses = {n['node_id'] for n in after['nodes'] if n['kind'] == 'hypothesis'}
    delta['reassessed_hypothesis_ids'] = sorted({e['target'] for e in edges if e['target'] in hypotheses and e['kind'] in ('supports', 'weakens', 'contradicts', 'context_for')})
    return delta
