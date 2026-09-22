import unittest
from news.investigate import _validate_detailed
class Tests(unittest.TestCase):
 def setUp(self):
  self.ids={'a':{'title':'Nvidia and Nokia announce a $1 billion investment','summary':'Nvidia and Nokia announced a new investment.','ranking':{'commentary':False}}}
 def test_valid(self):
  obj={'hypotheses':[{'event':'Nvidia and Nokia announce an investment','mechanism':'Could support the stock price','evidence_id':'a','evidence_quote':'Nvidia and Nokia announce a $1 billion investment'}]}
  good,errors=_validate_detailed(obj,self.ids,4.0);self.assertEqual(len(good),1);self.assertEqual(errors,[])
 def test_bad_id(self):
  obj={'hypotheses':[{'event':'Deal','mechanism':'Possible support','evidence_id':'wrong','evidence_quote':'Nvidia and Nokia announce a $1 billion investment'}]}
  self.assertIn('hypothesis_1:unknown_evidence_id',_validate_detailed(obj,self.ids)[1])
 def test_unsupported_profit_taking(self):
  obj={'hypotheses':[{'event':'Deal','mechanism':'Investors took profit-taking after news','evidence_id':'a','evidence_quote':'Nvidia and Nokia announce a $1 billion investment'}]}
  self.assertIn('hypothesis_1:unsupported_mechanism',_validate_detailed(obj,self.ids)[1])
 def test_bad_schema(self):
  self.assertEqual(_validate_detailed(None,self.ids)[1],['invalid_json_schema'])
if __name__=='__main__':unittest.main()
