import unittest
from news.event_grouping import group_articles
from news.investigate import _validate_detailed

class GroupingTests(unittest.TestCase):
 def test_nokia_reports_group(self):
  a={'id':'a','title':'NVIDIA To Make $1B Equity Investment In Nokia'}
  b={'id':'b','title':'NVIDIA And Nokia Form Strategic Alliance To Accelerate AI-Native Mobile Networks'}
  self.assertEqual(len(group_articles([a,b])),1)
 def test_unrelated_news_separate(self):
  a={'id':'a','title':'Nvidia to invest in Nokia'}
  b={'id':'b','title':'Nvidia CEO says demand is sky high'}
  self.assertEqual(len(group_articles([a,b])),2)
 def test_quote_whitespace_repaired_to_source(self):
  article={'id':'a','title':'Nvidia announces a strategic partnership with Nokia','summary':'','ranking':{'commentary':False}}
  hypothesis={'hypotheses':[{'event':'Nvidia announces partnership','mechanism':'Could improve sales and lift shares','evidence_id':'a','evidence_quote':'Nvidia announces a strategic   partnership with Nokia'}]}
  good,errors=_validate_detailed(hypothesis,{'a':article},4)
  self.assertEqual(errors,[])
  self.assertEqual(good[0]['evidence_quote'],article['title'])
 def test_fake_quote_rejected(self):
  article={'id':'a','title':'Nvidia announces a strategic partnership with Nokia','summary':'','ranking':{'commentary':False}}
  hypothesis={'hypotheses':[{'event':'Nvidia announces partnership','mechanism':'Could lift shares','evidence_id':'a','evidence_quote':'Nvidia announces a billion-dollar investment in Nokia'}]}
  good,errors=_validate_detailed(hypothesis,{'a':article},4)
  self.assertEqual(errors,['hypothesis_1:unsupported_evidence_quote'])
if __name__=='__main__': unittest.main()
