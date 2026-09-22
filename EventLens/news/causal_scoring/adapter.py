"""Evidence-linked scoring adapter. Never fabricate missing semantic criterion values."""
from datetime import datetime
from .models import (CandidateAssessment, CriterionScore, CriterionMethod,
                     EvidenceItem, EvidenceRole, EvidenceStance)
from .scorer import CausalCandidateScorer

SEMANTIC = ('relationship_directness', 'economic_plausibility', 'materiality',
            'directional_consistency', 'novelty', 'market_footprint_fit')

def _criterion(name, raw, evidence_id):
    item = raw.get(name) if isinstance(raw, dict) else None
    if not isinstance(item, dict):
        return CriterionScore(value=None, rationale='Not assessed; no model/human judgement supplied.', method=CriterionMethod.MODEL_JUDGMENT)
    value, rationale = item.get('value'), item.get('rationale')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1 or not isinstance(rationale, str) or not rationale.strip():
        return CriterionScore(value=None, rationale='Invalid or missing assessment.', method=CriterionMethod.MODEL_JUDGMENT)
    return CriterionScore(value=float(value), rationale=rationale[:600], evidence_ids=(evidence_id,), method=CriterionMethod.MODEL_JUDGMENT)

def score_group(event, article, hypothesis, cutoff, semantic=None):
    """Score one validated hypothesis. Representative article only; no invented independent sources."""
    published = datetime.fromisoformat(article['published_at'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(cutoff.replace('Z', '+00:00'))
    # Daily data cannot establish intraday anomaly onset: use start of market day.
    from datetime import timedelta
    start = end - timedelta(hours=6, minutes=30)
    if published.tzinfo is None or end.tzinfo is None:
        raise ValueError('Timezone-aware timestamps required')
    evidence_id = article['id']
    evidence = EvidenceItem(evidence_id=evidence_id, source_name=article.get('source') or 'Unknown',
                            source_uri=article.get('url') or None, published_at=published,
                            lineage_id=evidence_id, role=EvidenceRole.SECONDARY_ANALYSIS,
                            stance=EvidenceStance.SUPPORTS)
    # Reporting lineage cannot be inferred from grouped article IDs; do not count them as independent.
    assessment = CandidateAssessment(anomaly_id=str(event['date']), candidate_event_id=evidence_id,
        anomaly_start_at=start, anomaly_end_at=end, as_of_at=end, evidence=(evidence,),
        **{name: _criterion(name, semantic, evidence_id) for name in SEMANTIC})
    result = CausalCandidateScorer().score(assessment)
    return {'event':hypothesis['event'], 'hypothesis':hypothesis, 'assessment':assessment.model_dump(mode='json'),
            'result':result.model_dump(mode='json'), 'limitations':[
              'LLM criterion scores are uncalibrated judgements, not verified entailment or causal probabilities.',
              'Only representative source included; independent reporting and primary sources require separate verification.',
              'Daily anomaly onset approximated by session open; no intraday timing claim.']}
