import unittest
from news.investigate import _parse_json, _classify_relationship

class ResponseContractTests(unittest.TestCase):
    def test_valid_decision(self):
        self.assertEqual(_parse_json('{"status":"insufficient_evidence","reason":"no source","hypothesis":null}')['status'], 'insufficient_evidence')
    def test_empty_response(self):
        self.assertIsNone(_parse_json(''))
    def test_generic_issuer_not_hardcoded(self):
        self.assertEqual(_classify_relationship({}, {'title':'ACME shares rose after a deal', 'summary':'ACME stock gained'}), 'plausible_unverified_link')

if __name__ == '__main__': unittest.main()
