import unittest
from datetime import datetime, timezone
from news.ranker import rank_articles, score_article
from news.investigate import _validate

NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)
def article(id, title, summary=''):
    return {'id':id, 'title':title, 'summary':summary, 'published_at':'2026-09-19T12:00:00+00:00'}

class GenericTests(unittest.TestCase):
    def test_company_name(self):
        a=article('a','Apple announces earnings')
        self.assertTrue(score_article(a,'AAPL',NOW,'Apple Inc.')['company_mentioned'])
        self.assertFalse(score_article(a,'AAPL',NOW)['company_mentioned'])
    def test_unknown_ticker_not_dropped(self):
        ranked, matches=rank_articles([article('a','Company announces acquisition')], 'XYZ', NOW)
        self.assertEqual((len(ranked),matches),(1,0))
    def test_no_vendor_terms(self):
        self.assertNotIn('blackwell', str(__import__('news.ranker',fromlist=['EVENT_TERMS']).EVENT_TERMS).lower())
    def test_validator_accepts_other_ticker_event(self):
        a=article('a','Apple announces new supply agreement')
        obj={'hypotheses':[{'event':'Apple announces new supply agreement','mechanism':'May affect supply outlook, but effect is uncertain','evidence_id':'a','evidence_quote':a['title']}]}
        self.assertIsNotNone(_validate(obj, {'a':a}))

if __name__=='__main__': unittest.main()
