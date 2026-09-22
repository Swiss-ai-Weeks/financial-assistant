import importlib
m = importlib.import_module('news.investigate')
def group(title,score,day):return [{'title':title,'summary':'','ranking':{'score':score,'same_day':day}}]
groups=[group('Nvidia partnership',.99,True),group('Nvidia stock tariff hits semiconductor stocks',.65,True),group('Nvidia investment',.9,False)]
selected,count=m._select_lanes(groups,3)
assert count==1 and len(selected)==3 and any('tariff' in g[0]['title'] for g in selected)
assert not m._macro_candidate({'title':'Nvidia partnership','summary':''})
print('PASS: macro lane selection, non-macro exclusion, compilation')
