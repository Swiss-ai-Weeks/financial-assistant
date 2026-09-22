"""Run from project root: python -m unittest discover -s tests -p test_lightweight_scoring.py"""
import unittest
from news.lightweight_scoring import _source_alignment, build_readiness


class AlignmentTests(unittest.TestCase):
    def test_multi_story_requires_review_not_rejection(self):
        result = _source_alignment('Blue Owl limits fund withdrawals, mortgage rates rise',
                                   'Tesla deliveries miss estimates',
                                   'Tesla deliveries miss Wall Street estimates')
        self.assertEqual(result['status'], 'review_title_event_mismatch')

    def test_headline_overlap_does_not_claim_verification(self):
        result = _source_alignment('Tesla deliveries miss estimates',
                                   'Tesla deliveries miss estimates', '')
        self.assertEqual(result['status'], 'title_overlap_not_verified')

    def test_no_sections_fails(self):
        with self.assertRaises(ValueError):
            build_readiness('not an investigation')
