"""Offline integration regression: V16 model contract and independent scoring."""
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from news import investigate as investigation


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.usage_metadata = {'input_tokens': 35, 'output_tokens': 42}


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return FakeResponse(self.response)


class PipelineTests(unittest.TestCase):
    def _run(self, ticker, name):
        headline = f'{name} announces a new distribution partnership'
        article_id = f'{ticker}-source-1'
        article = {
            'id': article_id, 'title': headline, 'summary': headline,
            'source': 'Example', 'url': 'https://example.com/story',
            'published_at': '2025-10-28T14:00:00+00:00',
            'ranking': {'score': 0.91, 'event_specificity': 1.0,
                        'source_quality_proxy': 1.0, 'event_categories': ['commercial'],
                        'commentary': False},
            'event_group': {'article_ids': [article_id], 'members': []},
        }
        event = {'date': '2025-10-28', 'return_pct': 3.5, 'volume_zscore': 2.8}
        data = {'ticker': ticker, 'investigations': [{
            'event': event, 'window_start_utc': '2025-10-21T04:00:00+00:00',
            'cutoff_exclusive_utc': '2025-10-28T20:00:00+00:00',
            'market_close_et': '2025-10-28 16:00 America/New_York',
            'stored_articles': 1, 'lexically_relevant': 1,
            'evidence': [article], 'retrieval_macro_groups': 0,
            'retrieval_selected_macro_groups': 0, 'retrieval_day_groups': 1,
            'retrieval_older_groups': 0,
        }]}
        answer = json.dumps({'status': 'supported_hypothesis', 'reason': 'Documented event',
                             'hypothesis': {'event': headline,
                                            'mechanism': 'Potential downstream distribution pathway; not a verified price impact.',
                                            'evidence_id': article_id, 'evidence_quote': headline,
                                            'relationship_class': 'plausible_unverified_link'}})
        llm = FakeLLM(answer)
        fake_model = types.ModuleType('model')
        fake_model.llm = llm
        fake_msgs = types.ModuleType('langchain_core.messages')
        fake_msgs.SystemMessage = lambda content: ('system', content)
        fake_msgs.HumanMessage = lambda content: ('human', content)
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / 'report.txt')
            with patch.object(investigation, 'build_investigations', return_value=data), \
                 patch.dict(sys.modules, {'model': fake_model, 'langchain_core': types.ModuleType('langchain_core'),
                                          'langchain_core.messages': fake_msgs}):
                investigation.investigate({'ticker': ticker, 'company_name': name, 'events': [event]}, output=out)
            report = Path(out).read_text()
            scores = json.loads(Path(out + '.scores.json').read_text())
        return llm, report, scores

    def test_generic_issuers_preserve_one_call_and_score_sidecar(self):
        for ticker, name in (('ABCD', 'Alpha Group'), ('WXYZ', 'Beta Systems')):
            with self.subTest(ticker=ticker):
                llm, report, scores = self._run(ticker, name)
                self.assertEqual(len(llm.calls), 1)
                self.assertIn('supported_hypothesis', report)
                self.assertEqual(len(scores['scores']), 1)
                self.assertEqual(scores['scores'][0]['ticker'], ticker)
                self.assertEqual(scores['scores'][0]['result']['classification'], 'insufficient_evidence')
                self.assertIn('economic_plausibility', scores['scores'][0]['result']['missing_criteria'])
                self.assertNotIn('scoring_assessment', llm.calls[0][1][1])

    def test_scoring_error_does_not_erase_decision(self):
        with patch('news.causal_scoring.adapter.score_group', side_effect=ValueError('test failure')):
            llm, report, scores = self._run('ABCD', 'Alpha Group')
        self.assertEqual(len(llm.calls), 1)
        self.assertIn('supported_hypothesis', report)
        self.assertEqual(scores['scores'][0]['scoring_error'], 'ValueError: test failure')

    def test_issuer_lexical_checks_are_dynamic(self):
        self.assertTrue(investigation._issuer_mentioned('Alpha Group shares gained', ('ABCD', 'Alpha Group')))
        self.assertFalse(investigation._issuer_mentioned('Beta Systems shares gained', ('ABCD', 'Alpha Group')))
        self.assertEqual(investigation._classify_relationship({},
                         {'title': 'Alpha Group shares gained after announcement'},
                         ('ABCD', 'Alpha Group')), 'documented_market_link')
        self.assertEqual(investigation._classify_relationship({},
                         {'title': 'Beta Systems shares gained after announcement'},
                         ('ABCD', 'Alpha Group')), 'plausible_unverified_link')


if __name__ == '__main__':
    unittest.main()
