import unittest
from datetime import datetime, timezone
from news.causal_scoring.adapter import score_group
from news.causal_scoring.scorer import CausalCandidateScorer
from news.causal_scoring.models import CandidateAssessment

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.event={'date':'2025-10-28'}
        self.article={'id':'a1','published_at':'2025-10-28T14:00:00+00:00','title':'Nvidia announcement','source':'Example','url':'https://example.com/a'}
        self.hypothesis={'event':'Nvidia announcement'}
        self.cutoff='2025-10-28T20:00:00+00:00'
    def test_missing_semantics_stays_insufficient(self):
        x=score_group(self.event,self.article,self.hypothesis,self.cutoff)
        self.assertEqual(x['result']['classification'],'insufficient_evidence')
        self.assertIn('economic_plausibility',x['result']['missing_criteria'])
    def test_partial_semantics_stays_missing(self):
        x=score_group(self.event,self.article,self.hypothesis,self.cutoff,{'economic_plausibility':{'value':0.9,'rationale':'possible demand pathway'}})
        self.assertIsNone(x['result']['criteria']['relationship_directness']['value'])
    def test_future_evidence_ineligible(self):
        a=dict(self.article,published_at='2025-10-29T14:00:00+00:00')
        x=score_group(self.event,a,self.hypothesis,self.cutoff)
        self.assertFalse(x['result']['eligible'])
        self.assertEqual(x['result']['score'],0)
    def test_invalid_semantic_value_not_accepted(self):
        x=score_group(self.event,self.article,self.hypothesis,self.cutoff,{'economic_plausibility':{'value':1.4,'rationale':'bad'}})
        self.assertIsNone(x['result']['criteria']['economic_plausibility']['value'])
if __name__=='__main__': unittest.main()
