import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from news.selection import select_events
from news.ingest import ingest_anomaly_windows

class DemoPipelineFixTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 22)
        self.payload = {'ticker': 'TEST', 'events': [
            {'date': (self.today - timedelta(days=d)).isoformat(), 'return_pct': d}
            for d in [800, 400, 365, 300, 200, 100, 1]]}

    def test_demo_selects_three_reproducibly_without_mutation(self):
        selected = select_events(self.payload, today=self.today)
        self.assertEqual(len(selected['events']), 3)
        self.assertTrue(all(date.fromisoformat(e['date']) >= self.today - timedelta(days=365)
                            for e in selected['events']))
        self.assertEqual(selected['events'], select_events({**self.payload, 'events': list(reversed(self.payload['events']))}, today=self.today)['events'])
        self.assertEqual(len(self.payload['events']), 7)

    def test_production_uses_all_original_events(self):
        self.assertIs(select_events(self.payload, demo=False, today=self.today), self.payload)

    def test_ingestion_only_selected_days_and_event_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {'ticker':'TEST', 'events':[{'date':'2026-09-20'}, {'date':'2026-09-21'}, {'date':'2026-09-22'}]}
            source = Path(tmp)/'selected.json'
            source.write_text(json.dumps(payload))
            calls = []
            def fake(ticker, start, end, key):
                calls.append(start)
                return []
            with patch('news.ingest.fetch_finnhub', side_effect=fake):
                result = ingest_anomaly_windows(str(source), str(Path(tmp)/'news.sqlite'),
                                                days_before=7, include_event_day=True, request_interval=0)
            self.assertEqual(result['anomalies'], 3)
            self.assertEqual(result['days_requested'], 10)
            self.assertEqual(len(calls), 10)
            self.assertEqual(calls[-1], '2026-09-22')

if __name__ == '__main__': unittest.main()
