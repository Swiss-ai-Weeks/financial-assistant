import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from news.ingest import ingest_anomaly_windows

class ResumeTests(unittest.TestCase):
    def test_resume_skips_completed_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'anomalies.json'
            source.write_text(json.dumps({'ticker':'NVDA','events':[{'date':'2026-01-10'}]}))
            db=str(Path(tmp)/'news.sqlite')
            def fake(ticker,start,end,key):
                return [{'title':'Article','summary':'','source':'test','url':'https://example.org/'+start,'published_at':start+'T12:00:00Z'}]
            with patch('news.ingest.fetch_finnhub',side_effect=fake) as fetch:
                first=ingest_anomaly_windows(source,db,request_interval=0)
                second=ingest_anomaly_windows(source,db,request_interval=0)
            self.assertEqual(fetch.call_count,7)
            self.assertEqual(first['inserted'],7)
            self.assertEqual(second['skipped_days'],7)
            self.assertEqual(second['inserted'],0)

    def test_429_stops_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'anomalies.json'
            source.write_text(json.dumps({'ticker':'NVDA','events':[{'date':'2026-01-10'}]}))
            db=str(Path(tmp)/'news.sqlite')
            err=HTTPError('https://example.org',429,'Too Many Requests',{},None)
            with patch('news.ingest.fetch_finnhub',side_effect=err) as fetch, patch('news.ingest.time.sleep'):
                result=ingest_anomaly_windows(source,db,request_interval=0,max_retries=1)
            self.assertEqual(fetch.call_count,2)
            self.assertEqual(len(result['failed_days']),1)
            self.assertEqual(result['skipped_days'],0)
