import tempfile
import unittest
from pathlib import Path
from news.store import NewsStore
from news.retrieve import retrieve_evidence,format_context

class NewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.tmp.name)/'news.sqlite')
        self.store=NewsStore(self.path)
    def tearDown(self):
        self.store.close();self.tmp.cleanup()
    def test_dedup_and_future_exclusion(self):
        articles=[
          {'title':'Chip demand', 'summary':'AI chip demand', 'source':'Publisher', 'url':'https://example.com/a?utm_source=x', 'published_at':'2025-01-26T12:00:00Z'},
          {'title':'Future report', 'summary':'later', 'source':'Publisher', 'url':'https://example.com/b', 'published_at':'2025-01-28T12:00:00Z'}]
        self.assertEqual(self.store.add('NVDA',articles),2)
        self.assertEqual(self.store.add('NVDA',articles),0)
        result=retrieve_evidence('NVDA','2025-01-20T00:00:00Z','2025-01-27T00:00:00Z',db_path=self.path)
        self.assertEqual(result['count'],1)
        self.assertEqual(result['evidence'][0]['title'],'Chip demand')
        self.assertIn('https://example.com/a',format_context(result))
    def test_query_and_invalid_timestamps(self):
        self.store.add('NVDA',[{'title':'Chip demand','summary':'semiconductors','url':'https://example.com/a','published_at':'2025-01-26T12:00:00+00:00'}])
        result=retrieve_evidence('NVDA','2025-01-20T00:00:00Z','2025-01-27T00:00:00Z',query='chip',db_path=self.path)
        self.assertEqual(result['count'],1)
        with self.assertRaises(ValueError):
            self.store.search('NVDA','2025-01-20','2025-01-27')
    def test_empty_result_is_explicit(self):
        result=retrieve_evidence('NVDA','2025-01-20T00:00:00Z','2025-01-27T00:00:00Z',db_path=self.path)
        self.assertIn('NO NEWS EVIDENCE',format_context(result))

if __name__=='__main__':unittest.main()
