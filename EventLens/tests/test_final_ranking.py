import unittest
from news.final_ranking import build_ranking, render_markdown


def row(event, eid, score, flags=None, date='2026-04-02'):
    return {'ticker': 'TSLA', 'anomaly_date': date, 'hypothesis': {
        'event': event, 'evidence_id': eid, 'claim_flags': flags or [],
        'relationship_class': 'needs_review' if flags else 'plausible_unverified_link'},
        'result': {'score': score, 'classification': 'plausible',
                   'evidence_coverage': 1.0, 'missing_criteria': []}, 'retrieval_score': 0.5}


class FinalRankingTests(unittest.TestCase):
    def test_same_delivery_event_deduplicated_without_score_inflation(self):
        rows = [row('Q1 deliveries miss estimates', 'a', 20, ['needs_review']),
                row('Tesla Q1 deliveries missed Wall Street estimates', 'b', 83.4, ['needs_review']),
                row('Tesla Q1 2026 delivery miss reported', 'c', 76.7)]
        events = build_ranking({'scores': rows})['events']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['article_count'], 3)
        self.assertEqual(events[0]['causal_score'], 76.7)
        self.assertIsNone(events[0]['independent_source_count'])

    def test_audit_report_explains_selection_and_missing_criteria(self):
        rows = [row('Q1 deliveries miss', 'a', 83.4, ['needs_review']),
                row('Q1 deliveries miss', 'b', 76.7)]
        rows[0]['result']['missing_criteria'] = ['novelty']
        output = build_ranking({'scores': rows})
        md = render_markdown(output)
        self.assertIn('SELECTED `b`', md)
        self.assertIn('NOT SELECTED `a`', md)
        self.assertIn('claim_flags_require_review', md)
        self.assertIn('novelty', md)
        self.assertIn('independent sources: unknown', md)

    def test_different_quarters_and_days_not_merged(self):
        rows = [row('Q1 deliveries miss', 'a', 80), row('Q2 deliveries miss', 'b', 75),
                row('Q1 deliveries miss', 'c', 70, date='2026-04-03')]
        self.assertEqual(len(build_ranking({'scores': rows})['events']), 3)

    def test_no_score_blending_and_review_first(self):
        rows = [row('Unrelated product announcement', 'a', 99, ['needs_review']),
                row('Q1 deliveries miss', 'b', 70)]
        events = build_ranking({'scores': rows})['events']
        self.assertEqual(events[0]['causal_score'], 70)
        self.assertEqual(events[1]['status'], 'review_required')


if __name__ == '__main__':
    unittest.main()
