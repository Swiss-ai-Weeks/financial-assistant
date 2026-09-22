import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from news.ingest import ingest_anomaly_windows
from news.retrieve import retrieve_for_anomaly

class WindowTests(unittest.TestCase):
    def test_unique_days_and_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'anomalies.json'
            source.write_text(json.dumps({'ticker':'NVDA','events':[{'date':'2026-01-27'},{'date':'2026-01-29'}]}))
            calls=[]
            def fake(ticker,start,end,key):
                calls.append(start)
                return [{'title':'Article','summary':'news','source':'Example',
                         'url':'https://example.org/'+start,
                         'published_at':start+'T12:00:00Z'}]
            db=str(Path(tmp)/'news.sqlite')
            with patch('news.ingest.fetch_finnhub',side_effect=fake):
                result=ingest_anomaly_windows(source,db)
            self.assertEqual(result['days_requested'],9)
            self.assertEqual(len(calls),len(set(calls)))
            self.assertEqual(result['inserted'],9)
            evidence=retrieve_for_anomaly('NVDA','2026-01-27',db_path=db)
            self.assertEqual(evidence['count'],7)
            self.assertTrue(all(x['published_at'] < '2026-01-27' for x in evidence['evidence']))

if __name__=='__main__': unittest.main()
