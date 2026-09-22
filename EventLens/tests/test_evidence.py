from news.investigate import _normalize_evidence, _validate_detailed

def article(summary):
    return {'title':'Joby NVIDIA collaboration', 'summary':summary, 'ranking':{'commentary':False}}

def check(quote, summary, event='Joby announced collaboration with NVIDIA'):
    ids={'id':article(summary)}
    result, errors=_validate_detailed({'hypotheses':[{'event':event,'mechanism':'Potentially relevant to demand, unverified.','evidence_id':'id','evidence_quote':quote}]},ids)
    return result, errors

assert _normalize_evidence('NVIDIA&#39;s  A &amp; B') == "NVIDIA's A & B"
r,e=check("Joby announced NVIDIA's collaboration & platform",'Joby announced NVIDIA&#39;s collaboration &amp; platform')
assert len(r)==1 and not e,(r,e)
r,e=check('Unrelated invented sentence','Joby announced NVIDIA collaboration')
assert not r and 'hypothesis_1:unsupported_evidence_quote' in e
r,e=check('Joby announced NVIDIA collaboration','Joby announced NVIDIA collaboration', 'Joby announced $20 billion NVIDIA collaboration')
assert not r and 'hypothesis_1:unsupported_event_quantity' in e,(r,e)
r,e=check('Joby announced NVIDIA collaboration','Joby announced NVIDIA collaboration worth $20 billion', 'Joby announced $20 billion NVIDIA collaboration')
assert len(r)==1 and not e,(r,e)
print('PASS: HTML entities, invented quote rejection, material number validation (4 tests)')
