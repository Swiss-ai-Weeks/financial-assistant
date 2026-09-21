"""Compact typed analytical inputs; selection is not an evidential judgment."""
import json
import re
from dataclasses import dataclass, field
from typing import Any

from financial_assistant.domain import (ArgumentNodeKind, ExtractedClaim, Observation,
                                         Calculation, Inference, RelationKind)


@dataclass(frozen=True)
class EvidenceArgument:
    source_kind: ArgumentNodeKind
    source_id: str
    text: str
    provenance_summary: dict[str, Any]
    ranking: dict[str, Any] = field(default_factory=dict)

    def context(self):
        return dict(source_kind=self.source_kind.value, source_id=self.source_id,
                    text=self.text, provenance_summary=self.provenance_summary)


def evidence_argument(item):
    if isinstance(item, EvidenceArgument):
        return item
    if isinstance(item, ExtractedClaim):
        return EvidenceArgument(ArgumentNodeKind.CLAIM, item.claim_id, item.text,
            dict(claim_type=item.claim_type.value, source_quote=item.source_quote,
                 document_id=item.document_id, extraction_run_id=item.model_run_id))
    if isinstance(item, Observation):
        return EvidenceArgument(ArgumentNodeKind.OBSERVATION, item.observation_id,
            f'{item.name}: {item.value} {item.unit or ""}',
            dict(source_document_id=item.source_document_id, **_metadata(item.metadata)), item.metadata)
    if isinstance(item, Calculation):
        return EvidenceArgument(ArgumentNodeKind.CALCULATION, item.calculation_id,
            f'{item.label}: {item.value} {item.unit or ""}',
            dict(method='deterministic calculation, not model arithmetic', expression=item.expression,
                 input_observation_ids=item.input_observation_ids, input_calculation_ids=item.input_calculation_ids,
                 **_metadata(item.metadata)), item.metadata)
    if isinstance(item, Inference):
        return EvidenceArgument(ArgumentNodeKind.INFERENCE, item.inference_id, item.text,
            dict(method='model-derived inference, NOT a direct observation',
                 derived_from_ids=item.derived_from_ids, model_run_id=item.model_run_id))
    raise TypeError(f'Unsupported analytical evidence type: {type(item).__name__}')


def _metadata(metadata):
    return {k: v for k, v in metadata.items() if k in (
        'ticker', 'metric_id', 'concept', 'period_end', 'comparison_period', 'frequency',
        'available_at', 'formula_version', 'assumptions', 'warnings')}


def select_arguments(items, hypothesis, limit=16):
    """Bound per hypothesis to 1–20 items, retaining native identity and lineage.

    Kind budgets prevent SEC volume or a long document from monopolizing the
    context. Within kinds prefer term relevance, latest period, quarterly/trend
    summaries. Calculation inputs are de-prioritized as redundant observations.
    """
    if not 1 <= limit <= 20:
        raise ValueError('max_arguments must be between 1 and 20')
    arguments = [evidence_argument(item) for item in items]
    keys = [(a.source_kind, a.source_id) for a in arguments]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate analytical evidence identity')
    terms = set(re.findall(r'[a-z]{3,}', hypothesis.text.lower())) - {
        'the', 'and', 'may', 'because', 'company', 'reflect', 'that', 'with'}
    def rank(a):
        text = (a.text + ' ' + str(a.ranking.get('metric_id', ''))).lower().replace('_', ' ')
        overlap = len(terms & set(re.findall(r'[a-z]{3,}', text)))
        period = str(a.ranking.get('period_end', ''))
        metric = str(a.ranking.get('metric_id', ''))
        trend = any(t in metric for t in ('_qoq_', '_yoy_', '_trend', 'peer', 'sector'))
        return (overlap, period, a.ranking.get('frequency') == 'quarterly', trend)
    groups = {kind: sorted((a for a in arguments if a.source_kind == kind), key=rank, reverse=True)
              for kind in (ArgumentNodeKind.CLAIM, ArgumentNodeKind.CALCULATION,
                           ArgumentNodeKind.OBSERVATION, ArgumentNodeKind.INFERENCE)}
    selected = []
    for kind, budget in ((ArgumentNodeKind.CLAIM, 6), (ArgumentNodeKind.CALCULATION, 6),
                         (ArgumentNodeKind.OBSERVATION, 2), (ArgumentNodeKind.INFERENCE, 2)):
        if kind == ArgumentNodeKind.OBSERVATION:
            inputs = {id for a in selected for id in a.provenance_summary.get('input_observation_ids', ())}
            groups[kind].sort(key=lambda a: a.source_id in inputs)
        selected.extend(groups[kind][:budget])
    selected = selected[:limit]
    for group in groups.values():
        for argument in group:
            if len(selected) < limit and argument not in selected:
                selected.append(argument)
    return tuple(selected)


def relationship_diagnostics(assessments):
    kinds = ('claim', 'observation', 'calculation', 'inference')
    counts = {r.value: 0 for r in RelationKind}
    by_kind = {kind: dict(counts) for kind in kinds}
    for assessment in assessments:
        relation, kind = assessment.relation.value, assessment.source_kind.value
        counts[relation] += 1
        by_kind.setdefault(kind, {r.value: 0 for r in RelationKind})[relation] += 1
    return {'counts': counts, 'by_source_kind': by_kind}


def log_relationship_diagnostics(assessments):
    print('RELATIONSHIPS (diagnostics, not scores): ' + json.dumps(relationship_diagnostics(assessments)))
