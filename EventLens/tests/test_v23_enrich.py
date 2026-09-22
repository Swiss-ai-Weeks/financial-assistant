import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
import types
from news.causal_scoring.enrich import enrich_file, validate_assessment
from news.causal_scoring.adapter import score_group


class FakeResponse:
    usage_metadata = {'input_tokens': 25, 'output_tokens': 30}
    def __init__(self, content): self.content = content


class FakeLLM:
    def __init__(self, content): self.content, self.calls = content, 0
    def invoke(self, messages):
        self.calls += 1
        return FakeResponse(self.content)


class EnrichTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'articles.db'
        self.article = {'id':'ID1','ticker':'ABCD','title':'Alpha Corp announces logistics partnership',
                        'summary':'Alpha Corp announces logistics partnership to distribute components.',
                        'source':'Example','url':'https://example.com/alpha',
                        'published_at':'2025-10-28T12:00:00+00:00'}
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE articles (id TEXT,ticker TEXT,title TEXT,summary TEXT,source TEXT,url TEXT,published_at TEXT)')
            db.execute('INSERT INTO articles VALUES (?,?,?,?,?,?,?)', tuple(self.article[x] for x in
                       ('id','ticker','title','summary','source','url','published_at')))
        hypothesis = {'event':self.article['title'],'mechanism':'Potential logistics exposure',
                      'evidence_id':'ID1','evidence_quote':self.article['title']}
        score = score_group({'date':'2025-10-28'}, self.article, hypothesis, '2025-10-28T20:00:00+00:00')
        score.update(ticker='ABCD', anomaly_date='2025-10-28')
        self.source = self.root / 'v22.json'
        self.source.write_text(json.dumps({'scores':[score]}))
        self.output = self.root / 'v23.json'

    def test_one_call_reuse_without_second_investigation(self):
        phrase = self.article['title']
        answer = {'criteria': {'relationship_directness': {'value':0.9,'rationale':'Issuer named as partner','quote':phrase},
                               'economic_plausibility': {'value':0.5,'rationale':'Distribution channel','quote':phrase}}}
        fake = FakeLLM(json.dumps(answer))
        with patch.dict(sys.modules, {'langchain_core': types.ModuleType('langchain_core'), 'langchain_core.messages': types.SimpleNamespace(SystemMessage=lambda content: content, HumanMessage=lambda content: content)}):
            first = enrich_file(self.source,self.db,self.output,llm=fake)
            second = enrich_file(self.source,self.db,self.output,llm=fake)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(first['scores'][0]['enrichment_status'],'completed')
        self.assertEqual(first['scores'][0]['result']['criteria']['relationship_directness']['value'],.9)
        self.assertEqual(first['scores'][0]['result']['classification'],'insufficient_evidence')
        self.assertEqual(second['additional_requests'],1)
        self.assertIsNone(json.loads(self.source.read_text())['scores'][0]['assessment']['relationship_directness']['value'])

    def test_invented_quote_rejected_and_other_valid_criterion_kept(self):
        payload = {'criteria': {'relationship_directness': {'value':1,'rationale':'Claim','quote':'Invented numbers showing billions'},
                                'economic_plausibility': {'value':0.4,'rationale':'Distribution','quote':self.article['title']}}}
        actual=validate_assessment(payload,self.article)
        self.assertNotIn('relationship_directness',actual)
        self.assertIn('economic_plausibility',actual)

    def test_source_missing_no_call(self):
        with sqlite3.connect(self.db) as db: db.execute('DELETE FROM articles')
        fake=FakeLLM('{}')
        result=enrich_file(self.source,self.db,self.output,llm=fake)
        self.assertEqual(fake.calls,0)
        self.assertEqual(result['scores'][0]['enrichment_status'],'source_not_found')

    def test_failfast_no_extra_calls(self):
        fake=FakeLLM('not json')
        with patch.dict(sys.modules, {'langchain_core': types.ModuleType('langchain_core'), 'langchain_core.messages': types.SimpleNamespace(SystemMessage=lambda content: content, HumanMessage=lambda content: content)}):
            data=enrich_file(self.source,self.db,self.output,llm=fake,max_candidates=5)
        self.assertEqual(fake.calls,1)
        self.assertEqual(data['scores'][0]['enrichment_status'],'failed_no_retry')

    def test_cannot_overwrite_original(self):
        with self.assertRaises(ValueError): enrich_file(self.source,self.db,self.source,llm=FakeLLM('{}'))

if __name__=='__main__': unittest.main()
