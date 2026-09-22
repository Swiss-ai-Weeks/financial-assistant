import unittest
from datetime import datetime, timezone
from news.ranker import rank_articles
from news.investigate import _validate

class RankerTests(unittest.TestCase):
    def setUp(self):
        self.cutoff = datetime(2025,10,10,20,tzinfo=timezone.utc)
        self.articles = [
            dict(id='generic', title='Nvidia stock price levels', summary='', published_at='2025-10-10T19:00:00+00:00'),
            dict(id='tariff', title='Trump threatens tariffs; Nvidia chips face China customs scrutiny', summary='New tariff and export restrictions could affect Nvidia.', published_at='2025-10-10T15:00:00+00:00'),
            dict(id='other', title='Apple launches phone', summary='', published_at='2025-10-10T19:30:00+00:00'),
        ]
    def test_event_beats_generic_and_excludes_unrelated(self):
        ranked, count = rank_articles(self.articles, 'NVDA', self.cutoff)
        self.assertEqual((ranked[0]['id'], count), ('tariff', 2))
    def test_verbatim_and_id(self):
        ids = {'tariff': self.articles[1]}
        valid = {'hypotheses':[{'event':'Tariff threat','mechanism':'Could create uncertainty for chip demand.', 'evidence_id':'tariff', 'evidence_quote':'Nvidia chips face China customs scrutiny'}]}
        self.assertIsNotNone(_validate(valid, ids))
        valid['hypotheses'][0]['evidence_quote'] = 'Fabricated event never published'
        self.assertIsNone(_validate(valid, ids))
        valid['hypotheses'][0]['evidence_quote'] = 'Nvidia chips face China customs scrutiny'
        valid['hypotheses'][0]['evidence_id'] = 'fake'
        self.assertIsNone(_validate(valid, ids))
    def test_tautology(self):
        ids = {'tariff': self.articles[1]}
        self.assertIsNone(_validate({'hypotheses':[{'event':'NVDA rose on 2025-10-10','mechanism':'Maybe tariffs','evidence_id':'tariff','evidence_quote':'Nvidia chips face China customs scrutiny'}]}, ids))

if __name__ == '__main__': unittest.main()
