"""Offline evidence-readiness audit. No model calls, no inferred causal scores.

Reads the existing investigation audit; never changes ranking or validation.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from .clean_report import _parse

STOP = frozenset('the a an and or of for to in on with after as at by from is are was were stock shares tesla tsla news says report reports today how why what first quarter q1 q2 2026'.split())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) > 2 and w not in STOP}


def _source_alignment(title: str, event: str, excerpt: str) -> dict:
    """Conservative triage only: headline mismatch is not proof of false evidence.

    Compare event to headline AND quoted source text. If a multi-story summary
    includes an event absent from the headline, require a human to check the
    actual article and provenance instead of automatically rejecting it.
    """
    event_terms = _tokens(event)
    title_hits = sorted(event_terms & _tokens(title))
    excerpt_hits = sorted(event_terms & _tokens(excerpt))
    if not event_terms:
        status = 'unknown'
    elif title_hits:
        status = 'title_overlap_not_verified'
    elif excerpt_hits:
        status = 'review_title_event_mismatch'
    else:
        status = 'review_no_lexical_event_match'
    return {'status': status, 'event_terms': sorted(event_terms),
            'title_matches': title_hits, 'excerpt_matches': excerpt_hits,
            'note': 'Lexical triage only; neither overlap nor mismatch proves or disproves the claim.'}


def build_readiness(investigation_text: str) -> dict:
    sections = _parse(investigation_text)
    if not sections:
        raise ValueError('No investigation sections found')
    result = {'schema_version': 'scoring-readiness-v2', 'causal_scores_computed': 0,
              'note': 'Retrieval rank is not causality. No semantic numeric inputs supplied; no causal scores computed.',
              'anomalies': []}
    for sec in sections:
        groups = []
        for source in sec['sources']:
            group = sec['groups'].get(source['id'])
            alignment = _source_alignment(source['title'], group['event'] if group else '',
                                          group['excerpt'] if group else '')
            flags = [x.strip() for x in (group['flags'] if group else '').split(',') if x.strip()]
            if group is None:
                status = 'review_missing'
            elif group['status'] == 'validation_rejected':
                status = 'rejected'
            elif group['status'] != 'supported_hypothesis':
                status = 'not_supported'
            elif (group['relationship'] == 'needs_review' or flags or
                  alignment['status'].startswith('review_') or not group['excerpt']):
                status = 'review_required'
            else:
                status = 'candidate_unscored'
            review_reasons = []
            if group is None:
                review_reasons.append('missing_group_review')
            elif group['status'] == 'supported_hypothesis':
                if group['relationship'] == 'needs_review':
                    review_reasons.append('relationship_needs_review')
                if flags:
                    review_reasons.append('validator_claim_flags')
                if not group['excerpt']:
                    review_reasons.append('missing_source_excerpt')
                if alignment['status'].startswith('review_'):
                    review_reasons.append(alignment['status'])
            groups.append({'group_id': source['id'], 'title': source['title'],
                           'source_url': source['url'], 'retrieval_rank': len(groups)+1,
                           'retrieval_score': float(source['score']),
                           'investigation_status': group['status'] if group else None,
                           'relationship': group['relationship'] if group else None,
                           'event': group['event'] if group else None,
                           'model_interpretation': group['mechanism'] if group else None,
                           'source_excerpt': group['excerpt'] if group else None,
                           'source_alignment': alignment,
                           'reason': group['reason'] if group else 'Review missing',
                           'claim_flags': group['flags'] if group else '',
                           'review_reasons': review_reasons,
                           'scoring_readiness': status, 'causal_score': None})
        result['anomalies'].append({'date': sec['date'], 'groups': groups})
    return result


def main():
    parser = argparse.ArgumentParser(description='Export offline hypothesis evidence-readiness audit')
    parser.add_argument('--input', default='evidence/news_investigation.txt')
    parser.add_argument('--output', default='evidence/hypothesis_scoring_readiness.json')
    args = parser.parse_args()
    payload = build_readiness(Path(args.input).read_text(encoding='utf-8'))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Readiness exported: {target} ({sum(len(a['groups']) for a in payload['anomalies'])} groups; no causal scores)")


if __name__ == '__main__':
    main()
