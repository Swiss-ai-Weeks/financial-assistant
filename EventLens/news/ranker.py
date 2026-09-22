"""Explainable heuristic for news selection, not a probability of causation."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

EVENT_TERMS={
 'policy':('tariff','export control','export restriction','sanction','regulator','regulatory approval','antitrust','ban','license','scrutiny'),
 'financial':('earnings','guidance','revenue','profit','forecast','sales','dividend','buyback','downgrade','upgrade'),
 'commercial':('investment','deal','contract','partnership','acquisition','merger','order','agreement','alliance'),
 'operations':('launch','recall','production','outage','lawsuit','investigation','supply','demand','capacity'),
}
COMMENTARY=('stock is trading','stock price','shares rise','shares fall','stock surges','stock falls','is it time to buy','should you buy','valuation after','price levels','what is the next','stock to buy','stock market today','stocks to watch','investment ideas','why is','why it','buy zone','live coverage','market summary','top midday stories')
MULTI=('market summary','top midday stories','stocks to watch','investment ideas','stock market today','live coverage','feature highlights','stocks that','stocks to buy')

def contains(text,phrase):
 return bool(re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',text or '',re.I))

def company_aliases(ticker,company_name=None):
 aliases=[ticker.strip()]
 if isinstance(company_name,str) and company_name.strip():
  name=company_name.strip();aliases.append(name)
  short=re.sub(r'\s*,?\s+(?:Inc\.?|Incorporated|Corporation|Corp\.?|Ltd\.?|Limited|PLC|AG|SA|SE)$','',name,flags=re.I).strip()
  if short: aliases.append(short)
 return tuple(dict.fromkeys(a for a in aliases if a))

def score_article(article,ticker,cutoff,company_name=None):
 title=article.get('title') or '';summary=article.get('summary') or '';text=title+' '+summary
 aliases=company_aliases(ticker,company_name)
 direct=any(contains(title,a) for a in aliases);mentioned=direct or any(contains(summary,a) for a in aliases)
 categories=[k for k,terms in EVENT_TERMS.items() if any(contains(text,t) for t in terms)]
 title_event=any(contains(title,t) for terms in EVENT_TERMS.values() for t in terms)
 commentary=any(contains(title,t) for t in COMMENTARY)
 multi=any(contains(title,t) for t in MULTI) or title.count(';')>=2
 published=datetime.fromisoformat(article['published_at'].replace('Z','+00:00'))
 hours=max(0,(cutoff-published).total_seconds()/3600);freshness=max(0,1-hours/168)
 same_day=published.astimezone(ZoneInfo('America/New_York')).date()==cutoff.astimezone(ZoneInfo('America/New_York')).date()
 relevance=1 if direct else .6 if mentioned else 0
 event_strength=1 if title_event else .35 if categories else 0
 specificity=1 if direct and title_event and not multi else .3 if direct and not multi else 0
 source_quality=0 if multi else 1 # format-specific proxy, NOT publisher reliability
 # Less saturated than the previous 0.30R+0.35E+0.25D+0.10F-0.30C.
 score=(.25*relevance+.25*event_strength+.15*(1 if same_day else freshness*.5)
        +.05*freshness+.20*specificity+.10*source_quality-(.25 if commentary else 0))
 return {'score':round(max(0,min(1,score)),4),'relevance':relevance,'event_significance':event_strength,'time_proximity':round(freshness,4),'same_day':same_day,'commentary':commentary,'event_categories':categories,'company_mentioned':mentioned,'event_specificity':specificity,'source_quality_proxy':source_quality,'multi_story':multi}

def rank_articles(articles,ticker,cutoff,limit=12,company_name=None,deduplicate=True):
 from difflib import SequenceMatcher
 ranked=[{**a,'ranking':score_article(a,ticker,cutoff,company_name)} for a in articles]
 ranked=[a for a in ranked if a['ranking']['company_mentioned']]
 ranked.sort(key=lambda a:(-a['ranking']['score'],-datetime.fromisoformat(a['published_at'].replace('Z','+00:00')).timestamp(),a['id']))
 if not deduplicate:return ranked[:limit],len(ranked)
 selected=[];titles=[]
 for a in ranked:
  title=' '.join(re.sub(r'[^a-z0-9 ]',' ',(a.get('title') or '').casefold()).split())
  if title and any(SequenceMatcher(None,title,old).ratio()>=.90 for old in titles):continue
  selected.append(a);titles.append(title)
  if len(selected)>=limit:break
 return selected,len(ranked)
