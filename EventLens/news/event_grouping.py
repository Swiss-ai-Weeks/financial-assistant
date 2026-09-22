"""Precision-first event grouping: matching counterparties, type, status and details."""
import re
from datetime import datetime
from difflib import SequenceMatcher

STOP = set('a an the and or of for with to in on at by from as is are was were will says said stock shares today ai new us market company companies news billion million investment invest investing deal partnership alliance agreement report reportedly'.split())
TYPES = {
    'investment': ('investment','invest','investing','equity','stake','funding'),
    'partnership': ('partnership','alliance','collaboration','collaborate','partner'),
    'approval': ('approval','approved','approves','license','licenses','export'),
    'restriction': ('tariff','restriction','ban','blocked','stalled','scrutiny','sanction'),
    'earnings': ('earnings','revenue','guidance','profit','sales'),
}
NEGATIVE = ('snag','stalled','blocked','denied','halted','paused','delay','concerns')
PENDING = ('reportedly','nears','plans','plan','proposed','talks','may','could')
CONFIRMED = ('approved','announces','announced','confirmed','completed','finalized','launches','launched')
GENERIC = set('ai artificial intelligence stock stocks market shares investors tech technology company companies open source today'.split())

def words(text):
    return set(re.findall(r'[a-z0-9]+', (text or '').casefold()))

def signature(article):
    title = (article.get('title') or '').casefold()
    w = words(title)
    types = {kind for kind, terms in TYPES.items() if any(re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',title) for t in terms)}
    # Specific named counterparties, products and numeric details must be shared.
    distinctive = w - STOP - GENERIC - set().union(*(words(' '.join(v)) for v in TYPES.values()))
    numbers = set(re.findall(r'\$\s*\d+(?:\.\d+)?\s*(?:billion|million|bn|m)?|\b\d+(?:\.\d+)?\s*(?:billion|million|bn)\b',title))
    status = 'negative' if any(t in w for t in NEGATIVE) else 'pending' if any(t in w for t in PENDING) else 'confirmed' if any(t in w for t in CONFIRMED) else 'unspecified'
    return types, distinctive, numbers, status

def related(a,b):
    ta,ea,na,sa=signature(a); tb,eb,nb,sb=signature(b)
    if sa != sb and sa != 'unspecified' and sb != 'unspecified': return False
    if ta and tb and not (ta & tb): return False
    if na and nb and not (na & nb): return False
    try:
        da=datetime.fromisoformat(a['published_at'].replace('Z','+00:00'))
        db=datetime.fromisoformat(b['published_at'].replace('Z','+00:00'))
        if abs((da-db).total_seconds()) > 72*3600: return False
    except (KeyError,ValueError,TypeError): pass
    shared=ea & eb
    if not shared: return False
    # A single generic shared word is not enough to merge distinct events.
    if len(shared) < 2 and not (na and nb and na & nb): return False
    wa=words(a.get('title')); wb=words(b.get('title'))
    similarity=len(wa & wb)/max(1,len(wa | wb))
    return similarity >= .32 or (len(shared)>=3 and bool(ta & tb))

def group_articles(ranked):
    groups=[]
    for article in ranked:
        match=next((g for g in groups if all(related(article,m) for m in g)),None)
        if match is None: groups.append([article])
        else: match.append(article)
    return groups

def rank_groups(groups):
    return sorted(groups,key=lambda g:-max(a['ranking']['score'] for a in g))
