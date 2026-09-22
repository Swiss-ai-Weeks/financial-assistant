import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import news_cli


class DemoSelectionTests(unittest.TestCase):
    def test_three_reproducible_and_filtered(self):
        payload = {'ticker': 'NVDA', 'events': [{'date': d} for d in
                   ['2025-09-30', '2025-10-02', '2025-11-01', '2026-01-01', '2026-02-01']]}
        result = news_cli.select_demo_events(payload)
        self.assertEqual(len(result['events']), 3)
        self.assertTrue(all(e['date'] >= '2025-10-01' for e in result['events']))
        self.assertEqual(result, news_cli.select_demo_events({'ticker': 'NVDA', 'events': list(reversed(payload['events']))}))
        self.assertEqual(len(payload['events']), 5)

    def test_disabled_preserves_payload(self):
        payload = {'ticker': 'NVDA', 'events': [{'date': '2024-01-01'}]}
        with patch.object(news_cli, 'DEMO', False):
            self.assertIs(news_cli.select_demo_events(payload), payload)


if __name__ == '__main__':
    unittest.main()
