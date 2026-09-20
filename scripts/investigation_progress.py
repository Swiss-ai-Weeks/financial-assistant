"""Bounded execution metadata only; never retain pipeline inputs or exception text."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
import re
from uuid import uuid4

COUNTS = frozenset('fundamental_facts_selected fundamental_metrics_calculated research_tasks search_hits retrieval_records query_expansions documents_selected documents claims hypotheses audits relationships model_runs nodes edges'.split())
COMPLETIONS = {'fundamentals_complete': 'financial_metrics', 'research_plan': 'research_plan', 'retrieval_complete': 'retrieval',
               'evidence_selection': 'evidence_selection', 'graph_complete': 'graph_build',
               **{f'{stage}_complete': stage for stage in ('claim_extraction', 'hypothesis_generation', 'hypothesis_audit', 'relationship_assessment')}}
MESSAGES = dict(fundamentals='Loading historical fundamentals', financial_metrics='Calculating financial metrics',
    fundamentals_complete='Fundamentals enrichment complete', preparing='Preparing investigation', research_plan='Research plan created',
    retrieval='Searching BookReader and the web', retrieval_complete='Retrieval complete',
    evidence_selection='Historical evidence selected', claim_extraction='Extracting grounded claims',
    claim_extraction_complete='Grounded claims extracted', hypothesis_generation='Generating competing hypotheses',
    hypothesis_generation_complete='Competing hypotheses generated', hypothesis_audit='Auditing assumptions and evidence gaps',
    hypothesis_audit_complete='Hypotheses audited', relationship_assessment='Assessing claim-hypothesis relationships',
    relationship_assessment_complete='Relationships assessed', graph_build='Building ClaimGraph', graph_complete='ClaimGraph built',
    hindsight='Calculating separately held-out hindsight outcome', replay_save='Saving replay packet', complete='Investigation complete')

class ProgressRegistry:
    def __init__(self, capacity=64):
        self.capacity = capacity
        self._runs = OrderedDict()
        self._lock = Lock()

    def start(self, run_id=None):
        run_id = str(uuid4()) if run_id is None else run_id
        if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', run_id):
            raise ValueError('Invalid run_id')
        with self._lock:
            if run_id in self._runs:
                raise ValueError('run_id already exists')
            if len(self._runs) >= self.capacity:
                oldest = next((key for key, value in self._runs.items() if value['state'] != 'running'), None)
                if oldest is None:
                    raise ValueError('Too many active investigations')
                del self._runs[oldest]
            now = datetime.now(timezone.utc).isoformat()
            self._runs[run_id] = dict(run_id=run_id, state='running', stage='preparing',
                message=MESSAGES['preparing'], started_at=now, updated_at=now, completed=[], metrics={})
        return run_id

    def report(self, run_id, stage, message=None, metrics=None):
        with self._lock:
            run = self._runs[run_id]
            if run['state'] != 'running' or stage not in MESSAGES:
                return
            if run['stage'] in ('preparing', 'hindsight', 'replay_save') and stage != run['stage']:
                run['completed'].append(run['stage'])
            completed = COMPLETIONS.get(stage)
            if completed and completed not in run['completed']:
                run['completed'].append(completed)
            run.update(stage=stage, message=MESSAGES[stage], updated_at=datetime.now(timezone.utc).isoformat())
            run['metrics'].update({key: value for key, value in (metrics or {}).items()
                                   if key in COUNTS and type(value) is int and value >= 0})
            if stage == 'hindsight':
                run['hindsight_is_original_evidence'] = False
            if stage == 'complete':
                run['state'] = 'complete'

    def cutoff(self, run_id, observed_at):
        with self._lock:
            self._runs[run_id]['evidence_cutoff'] = observed_at.isoformat()

    def fail(self, run_id):
        with self._lock:
            self._runs[run_id].update(state='failed', message='Investigation failed; see server logs for details',
                                      updated_at=datetime.now(timezone.utc).isoformat())

    def get(self, run_id):
        with self._lock:
            return deepcopy(self._runs.get(run_id))

progress_registry = ProgressRegistry()
