"""Synthetic, issuer-neutral tests; no network, database, GPU, or real model."""
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from news import investigate as inv


class FakeResponse:
    def __init__(self, content, finish='stop', output_tokens=100):
        self.content = content
        self.response_metadata = {'done_reason': finish}
        self.additional_kwargs = {'reasoning_content': ''}
        self.usage_metadata = {'input_tokens': 55, 'output_tokens': output_tokens}


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.updates = []
        self.calls = 0

    def model_copy(self, update):
        self.updates.append(update)
        return self

    def invoke(self, messages):
        self.calls += 1
        if not self.replies:
            raise AssertionError('Unintended extra LLM call')
        outcome = self.replies.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def fake_data():
    evidence = []
    for index in range(2):
        identifier = 'article-' + str(index + 1)
        headline = 'ACME signs cloud supply contract with Beta Industries'
        evidence.append({
            'id': identifier, 'published_at': '2026-02-10T14:00:00+00:00',
            'title': headline, 'summary': headline,
            'source': 'Synthetic source', 'url': 'https://example.org/' + identifier,
            'ranking': {'score': 0.85, 'event_specificity': 1.0,
                        'source_quality_proxy': 0.8, 'event_categories': ['commercial'],
                        'commentary': False},
            'event_group': {'article_ids': [identifier], 'members': []},
        })
    item = {'event': {'date': '2026-02-10', 'return_pct': 3.0,
                      'volume_zscore': 2.5},
            'window_start_utc': '2026-02-03T05:00:00+00:00',
            'cutoff_exclusive_utc': '2026-02-10T21:00:00+00:00',
            'market_close_et': '2026-02-10 16:00 America/New_York',
            'stored_articles': 2, 'lexically_relevant': 2,
            'retrieval_day_groups': 2, 'retrieval_older_groups': 0,
            'retrieval_macro_groups': 0, 'retrieval_selected_macro_groups': 0,
            'evidence': evidence}
    return {'ticker': 'ABC', 'investigations': [item]}


class InvestigationContractTests(unittest.TestCase):
    def run_case(self, replies, environment=None):
        fake_llm = FakeLLM(replies)
        messages = types.ModuleType('langchain_core.messages')
        messages.SystemMessage = lambda content: ('system', content)
        messages.HumanMessage = lambda content: ('human', content)
        model = types.ModuleType('model')
        model.llm = fake_llm
        with tempfile.TemporaryDirectory() as folder:
            output = str(Path(folder) / 'investigation.txt')
            environ = {'NEWS_INVESTIGATE_MAX_REQUESTS': '0',
                       'NEWS_INVESTIGATE_FAIL_FAST': '1'}
            environ.update(environment or {})
            with (patch.dict(sys.modules, {'model': model,
                                           'langchain_core.messages': messages}),
                  patch.dict(os.environ, environ),
                  patch.object(inv, 'build_investigations', return_value=fake_data())):
                inv.investigate({'ticker': 'ABC', 'company_name': 'ACME',
                                 'events': []}, output=output)
            report = Path(output).read_text()
            diagnostic = json.loads(Path(output + '.diagnostics.json').read_text())
            scores = json.loads(Path(output + '.scores.json').read_text())
        return fake_llm, report, diagnostic, scores

    def test_valid_decisions_and_correct_options_not_bind_kwargs(self):
        reply = FakeResponse('{"status":"insufficient_evidence","reason":"No documented event","hypothesis":null}')
        model, report, diagnostics, scores = self.run_case([reply, reply])
        self.assertEqual(model.calls, 2)
        self.assertEqual(model.updates, [{'num_predict': 4096, 'format': 'json'}])
        self.assertIn('Review coverage: 2/2 groups', report)
        self.assertEqual(diagnostics['diagnostics'], [])
        self.assertEqual(scores['scores'], [])

    def test_invalid_schema_is_explained_and_fail_fast(self):
        reply = FakeResponse('{"answer":"some other structure"}', finish='length', output_tokens=4096)
        model, report, diagnostics, _ = self.run_case([reply])
        self.assertEqual(model.calls, 1)
        self.assertIn('Review coverage: 1/2 groups', report)
        self.assertIn('Stopped early', report)
        issue = diagnostics['diagnostics'][0]
        self.assertEqual(issue['error'], 'invalid_status')
        self.assertEqual(issue['finish_reason'], 'length')
        self.assertEqual(issue['parsed_keys'], ['answer'])
        self.assertEqual(issue['output_tokens'], 4096)

    def test_invocation_type_error_persisted_without_repeating(self):
        model, report, diagnostics, _ = self.run_case([TypeError('unexpected keyword argument num_predict')])
        self.assertEqual(model.calls, 1)
        self.assertIn('llm_error; reason=TypeError', report)
        self.assertEqual(diagnostics['diagnostics'][0]['exception_type'], 'TypeError')
        self.assertIn('unexpected keyword', diagnostics['diagnostics'][0]['exception_message'])

    def test_explicit_one_request_limit_is_reflected_in_coverage(self):
        reply = FakeResponse('{"status":"insufficient_evidence","reason":"No documented event","hypothesis":null}')
        model, report, _, _ = self.run_case([reply], {'NEWS_INVESTIGATE_MAX_REQUESTS': '1'})
        self.assertEqual(model.calls, 1)
        self.assertIn('Request cap reached: 1', report)
        self.assertIn('Review coverage: 1/2 groups', report)

    def test_supported_hypothesis_scores_without_claiming_causality(self):
        answer = {'status': 'supported_hypothesis', 'reason': 'A reported company event is present',
                  'hypothesis': {'event': 'ACME signs cloud supply contract with Beta Industries',
                                 'mechanism': 'The reported contract could affect expectations about future cloud infrastructure demand.',
                                 'evidence_id': 'article-1',
                                 'evidence_quote': 'ACME signs cloud supply contract with Beta Industries',
                                 'relationship_class': 'plausible_unverified_link'},
                  'scoring_assessment': {'economic_plausibility': {'value': 0.6, 'rationale': 'A possible demand connection'}}}
        replies = [FakeResponse(json.dumps(answer)), FakeResponse('{"status":"insufficient_evidence","reason":"None","hypothesis":null}')]
        model, report, diagnostics, scores = self.run_case(replies)
        self.assertEqual(model.calls, 2)
        self.assertEqual(len(scores['scores']), 1)
        self.assertIn('Causal score (research heuristic, not probability)', report)
        self.assertEqual(scores['scores'][0]['result']['criteria']['economic_plausibility']['value'], .6)
        self.assertEqual(diagnostics['diagnostics'], [])

    def test_issuer_reference_is_general_and_no_guessing(self):
        self.assertTrue(inv._source_mentions_issuer('ABC and Acme published a notice', 'ABC', 'ACME'))
        self.assertTrue(inv._source_mentions_issuer('OtherCorp shares fell', 'OTC', 'OtherCorp'))
        self.assertFalse(inv._source_mentions_issuer('Technology stocks fell', 'OTC', 'OtherCorp'))
        self.assertEqual(inv._classify_relationship({}, {'title': 'OtherCorp shares rose'}),
                         'plausible_unverified_link')

    def test_schema_discrimination(self):
        self.assertEqual(inv._decision_schema_issue(None), 'not_a_json_object')
        self.assertEqual(inv._decision_schema_issue({'status': 'unknown', 'reason': 'x'}), 'invalid_status')
        self.assertEqual(inv._decision_schema_issue({'status': 'context_only', 'reason': None}),
                         'missing_or_invalid_reason')


if __name__ == '__main__':
    unittest.main()
