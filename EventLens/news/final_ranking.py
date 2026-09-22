"""Conservative offline presentation ranking of already-scored hypotheses.

Does not rescore, infer reporting independence, or modify investigation outputs.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def _event_key(row):
    """Merge narrowly identified delivery misses for the same ticker/date."""
    event = str((row.get("hypothesis") or {}).get("event") or "").lower()

    normalized = re.sub(r"\bfirst[\s-]+quarter\b", "q1", event)
    normalized = re.sub(r"\bsecond[\s-]+quarter\b", "q2", normalized)
    normalized = re.sub(r"\bthird[\s-]+quarter\b", "q3", normalized)
    normalized = re.sub(r"\bfourth[\s-]+quarter\b", "q4", normalized)

    tokens = set(re.findall(r"[a-z0-9]+", normalized))

    delivery = bool(tokens & {"delivery", "deliveries"})
    miss = bool(tokens & {
        "miss", "missed", "missing", "shortfall", "below"
    })
    quarter = next(
        (q for q in ("q1", "q2", "q3", "q4") if q in tokens),
        None,
    )

    if delivery and miss and quarter:
        return f"delivery_miss:{quarter}"

    return (
        "individual:"
        + str(
            (row.get("hypothesis") or {}).get("evidence_id")
            or id(row)
        )
    )


def _status(row):
    result = row.get('result') or {}
    hypothesis = row.get('hypothesis') or {}
    flags = hypothesis.get('claim_flags') or []
    reasons = []
    if row.get('scoring_error') or not result:
        reasons.append('scoring_error_or_missing_result')
    if flags:
        reasons.append('claim_flags_require_review')
    if hypothesis.get('relationship_class') == 'needs_review':
        reasons.append('relationship_requires_review')
    if result.get('missing_criteria') or result.get('classification') in ('insufficient_evidence', 'ineligible'):
        reasons.append('incomplete_or_ineligible_assessment')
    # A full set of LLM numbers is not a fact-check; retain audit limitation.
    return ('review_required' if reasons else 'scored_unverified'), reasons


def build_ranking(data):
    if not isinstance(data, dict) or not isinstance(data.get('scores'), list):
        raise ValueError('Expected scoring sidecar with scores list')
    groups = defaultdict(list)
    for row in data['scores']:
        if not isinstance(row, dict):
            raise ValueError('Invalid score row')
        key = (str(row.get('ticker') or ''), str(row.get('anomaly_date') or ''), _event_key(row))
        groups[key].append(row)
    output = []
    for (ticker, day, event_key), rows in groups.items():
        audited = [(_status(row), row) for row in rows]
        clean = [row for (status, _), row in audited if status == 'scored_unverified']
        # No averaging/max across duplicates as a new causal score. Pick a representative
        # and explicitly disclose its provenance and other assessments.
        pool = clean or rows
        representative = max(pool, key=lambda r: (
            float((r.get('result') or {}).get('evidence_coverage') or 0),
            float((r.get('result') or {}).get('score') or 0),
            float(r.get('retrieval_score') or 0)))
        rep_status, rep_reasons = _status(representative)
        event_review_reasons = sorted({reason for (status, reasons), row in audited for reason in reasons})
        event_status = ("review_required" if event_review_reasons else "scored_unverified")

        ids = sorted({str(r.get('hypothesis', {}).get('evidence_id')) for r in rows if r.get('hypothesis', {}).get('evidence_id')})
        output.append({
            'ticker': ticker, 'anomaly_date': day, 'event_key': event_key,
            'event': representative.get('hypothesis', {}).get('event'),
            'status': event_status,
            'review_reasons': event_review_reasons,
            'score_method': 'selected_assessment_not_pooled',
            'representative_evidence_id': representative.get('hypothesis', {}).get('evidence_id'),
            'article_ids': ids, 'article_count': len(ids),
            'independent_source_count': None,
            'causal_score': (representative.get('result') or {}).get('score'),
            'classification': (representative.get('result') or {}).get('classification'),
            'evidence_coverage': (representative.get('result') or {}).get('evidence_coverage'),
            'retrieval_score': representative.get('retrieval_score'),
            'assessments': [{
                'evidence_id': r.get('hypothesis', {}).get('evidence_id'),
                'score': (r.get('result') or {}).get('score'),
                'classification': (r.get('result') or {}).get('classification'),
                'status': status, 'review_reasons': reasons,
                'missing_criteria': (r.get('result') or {}).get('missing_criteria') or [],
                'claim_flags': (r.get('hypothesis') or {}).get('claim_flags') or [],
                'relationship_class': (r.get('hypothesis') or {}).get('relationship_class'),
                'evidence_coverage': (r.get('result') or {}).get('evidence_coverage'),
                'representative': r is representative,
            } for (status, reasons), r in audited],
            'limitations': [
                'Event matching is narrow and heuristic; verify event identity manually.',
                'Representative score is not recomputed from pooled evidence.',
                'Article count is not independent-source count.',
                'LLM criterion scores are uncalibrated and not causal probabilities.',
                'Daily anomaly timing does not establish that news preceded the price move.',
            ],
        })
    # Order only within each ticker/day; review rows are never presented as verified.
    output.sort(key=lambda r: (r['ticker'], r['anomaly_date'],
        0 if r['status'] == 'scored_unverified' else 1,
        -(r['causal_score'] if isinstance(r['causal_score'], (int, float)) else -1),
        -(r['retrieval_score'] if isinstance(r['retrieval_score'], (int, float)) else -1), r['event_key']))
    return {'schema_version': 'final-ranking-audit-v1', 'method': 'review status, then representative causal score, retrieval tie-break only',
            'ranking_is_not_causal_proof': True, 'events': output}


def render_markdown(data):
    """Audit-friendly presentation; never turns an unverified score into causal proof."""
    md = ['# Final hypothesis ranking (audit-first)', '',
          'Scores are uncalibrated judgments, not causal probabilities. Article counts are not independent-source counts.',
          'Review status is an automated flag check, not independent verification.', '']
    for item in data['events']:
        md.extend([f"## {item['ticker']} | {item['anomaly_date']} | {item['event']}",
                   f"- Status: {item['status']}; representative causal score: {item['causal_score']}; retrieval: {item['retrieval_score']}",
                   f"- Representative evidence: `{item['representative_evidence_id']}`; articles grouped: {item['article_count']}; independent sources: unknown",
                   '- Selection rule: prefer candidates without automated review flags; then evidence coverage, causal score, and retrieval tie-break. This does not validate the underlying judgments.',
                   '', '### Candidate audit', ''])
        for assessment in item['assessments']:
            selected = assessment.get('representative', assessment.get('evidence_id') == item['representative_evidence_id'])
            md.extend([f"- {'SELECTED' if selected else 'NOT SELECTED'} `{assessment['evidence_id']}`: "
                       f"score={assessment['score']}, classification={assessment['classification']}, "
                       f"status={assessment['status']}, coverage={assessment.get('evidence_coverage', 'unknown')}",
                       f"  - Automated review reasons: {', '.join(assessment['review_reasons']) or 'none; manual verification still required'}",
                       f"  - Claim flags: {', '.join(assessment.get('claim_flags') or []) or 'none'}; "
                       f"relationship: {assessment.get('relationship_class') or 'unknown'}",
                       f"  - Missing semantic criteria: {', '.join(assessment.get('missing_criteria') or []) or 'none'}"])
        md.extend(['', '### Evidence limitations', ''])
        md.extend(f'- {limitation}' for limitation in item['limitations'])
        md.append('')
    return '\n'.join(md) + '\n'

def main():
    parser = argparse.ArgumentParser(description='Offline, audit-first hypothesis ranking')
    parser.add_argument('--input', default='evidence/news_investigation.txt.scores.json')
    parser.add_argument('--output', default='evidence/final_ranking.json')
    args = parser.parse_args()
    data = build_ranking(json.loads(Path(args.input).read_text(encoding='utf-8')))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md = render_markdown(data)
    path.with_suffix('.md').write_text(md, encoding='utf-8')
    print(f"Saved {path} and {path.with_suffix('.md')} ({len(data['events'])} event groups)")


if __name__ == '__main__':
    main()
