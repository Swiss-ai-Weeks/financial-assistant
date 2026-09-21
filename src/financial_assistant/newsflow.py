"""Pythia discovery wire. No graph mutations or model calls belong here."""
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path

import yfinance as yf
from .instruments import company_name
from .retrieval.archive import archive_items

LEGAL = {'the', 'inc', 'corp', 'corporation', 'company', 'co', 'companies', 'group', 'holdings', 'plc', 'ltd', '&'}
GENERIC = {'american', 'bank', 'first', 'general', 'home', 'international', 'national', 'united'}
CONNECTING = {'of', 'and', 'the', '&', 'de', 'for'}


def company_aliases(ticker, company):
    words = [w.strip(',.') for w in company.split() if w.strip(',.').lower() not in LEGAL]
    aliases = {ticker}
    if words and company != ticker:
        aliases.add(' '.join(words))
        if len(words) >= 2 and words[1].lower() not in CONNECTING:
            aliases.add(' '.join(words[:2]))
        if len(words[0]) >= 5 and words[0].lower() not in GENERIC:
            aliases.add(words[0])
    return tuple(sorted(aliases))


def relevance(item, aliases):
    def mentions(text):
        return any(re.search(rf'(?<!\w){re.escape(a)}(?!\w)', text or '', re.I) for a in aliases)
    return 2 if mentions(item['title']) else 1 if mentions(item.get('summary')) else 0


def timestamp(value, date_only=False):
    raw = str(value)
    stamp = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if date_only or len(raw) == 10:
        return datetime.combine(stamp.date(), datetime.max.time(), timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError('Publication timestamp needs a timezone')
    return stamp.astimezone(timezone.utc)


def one_per_story(items):
    best = {}
    for item in items:
        key = (re.sub(r'[^a-z0-9]', '', item['title'].lower()), item['published_at'][:10])
        previous = best.get(key)
        provenance = (previous or {}).get('provenance', []) + item.get('provenance', [])
        quality = lambda i: ('finnhub.io' not in i['url'], len(i.get('summary') or ''))
        chosen = dict(item if previous is None or quality(item) > quality(previous) else previous)
        # Use the latest reported publication time: dedup must never backdate a story.
        if previous:
            chosen['published_at'] = max(previous['published_at'], item['published_at'])
            chosen['relevance'] = max(previous.get('relevance', 0), item.get('relevance', 0))
            chosen['published_date_only'] = previous.get('published_date_only', False) or item.get('published_date_only', False)
        chosen['provenance'] = list({json.dumps(p, sort_keys=True): p for p in provenance}.values())
        best[key] = chosen
    return list(best.values())


class YahooNewsSource:
    name = 'yahoo-finance'

    def fetch(self, ticker):
        items = []
        for entry in yf.Ticker(ticker).get_news(count=200, tab='news'):
            content = entry.get('content') or {}
            url = (content.get('canonicalUrl') or {}).get('url') or (content.get('clickThroughUrl') or {}).get('url')
            if not url or not content.get('title') or not content.get('pubDate'):
                continue
            items.append(dict(news_id='NEWS-' + sha1(url.encode()).hexdigest()[:12],
                ticker=ticker, title=content['title'].strip(), url=url,
                publisher=(content.get('provider') or {}).get('displayName'),
                published_at=content['pubDate'], summary=(content.get('summary') or '').strip(), source=self.name))
        return items


class NewsRepository:
    """Accumulate Yahoo's rolling window; read the archive on every request."""
    def __init__(self, cache_dir=None, yahoo=None, archive_dir=None, cache_seconds=900):
        self.cache_dir = Path(cache_dir or os.environ.get('PYTHIA_NEWS_CACHE', 'data/cache/pythia_news'))
        self.yahoo = yahoo or YahooNewsSource()
        self.archive_dir = archive_dir
        self.cache_seconds = cache_seconds
        self.lock = threading.Lock()
        self.refreshed = {}

    def get(self, ticker):
        if not re.fullmatch(r'[A-Z0-9.^=_-]{1,30}', ticker):
            raise ValueError('Invalid ticker')
        statuses = {}
        try:
            local = archive_items(self.archive_dir, ticker=ticker, include_hindsight=True)
            statuses['pythia_archive'] = 'available' if local else 'empty'
        except OSError:
            local = []
            statuses['pythia_archive'] = 'unavailable'
        with self.lock:
            path = self.cache_dir / f'{ticker}.json'
            try:
                known = json.loads(path.read_text())
                if not isinstance(known, list):
                    known = []
            except (OSError, ValueError):
                known = []
            last, status = self.refreshed.get(ticker, (0, 'not_requested'))
            if time.monotonic() - last >= self.cache_seconds:
                try:
                    fetched = self.yahoo.fetch(ticker)
                    known = list({i['news_id']: i for i in [*known, *fetched]}.values())
                    status = 'available'
                except Exception:
                    status = 'unavailable'
                self.refreshed[ticker] = (time.monotonic(), status)
                if status == 'available':
                    try:
                        self.cache_dir.mkdir(parents=True, exist_ok=True)
                        temporary = path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(known))
                        temporary.replace(path)
                    except OSError:
                        statuses['cache'] = 'unavailable'
            statuses['yahoo-finance'] = status
        return [*local, *known], statuses


repository = NewsRepository()


def news_feed(tickers, as_of, *, limit=200, days=180, repo=None, describe=None):
    if not 1 <= limit <= 500 or not 1 <= days <= 800:
        raise ValueError('News limit must be 1–500 and days 1–800')
    cutoff = timestamp(as_of)
    start, end = cutoff - timedelta(days=days), cutoff + timedelta(days=3)
    candidates, statuses = [], {}
    for ticker in dict.fromkeys(t.strip().upper() for t in tickers if t.strip()):
        raw, status = (repo or repository).get(ticker)
        statuses[ticker] = status
        aliases = company_aliases(ticker, (describe or company_name)(ticker))
        for row in raw:
            try:
                item = dict(row)
                stamp = timestamp(item['published_at'], item.get('published_date_only', False))
                if not start <= stamp <= end or not item['url'].startswith(('https://', 'http://')) or not item['title']:
                    continue
                item.update(published_at=stamp.isoformat(), role='discovery_candidate', relevance=relevance(item, aliases),
                            published_date_only=item.get('published_date_only', False) or len(str(row['published_at'])) == 10)
                item['provenance'] = [dict(source=item.get('source'), publisher=item.get('publisher'), url=item['url'],
                                           published_at=row['published_at'], archive_source=item.get('archive_source'))]
                candidates.append(item)
            except (KeyError, ValueError, TypeError):
                continue
    candidates = one_per_story(candidates)
    candidates.sort(key=lambda i: (i['relevance'], i['published_at']), reverse=True)
    admissible, hindsight = [], []
    for item in candidates:
        allowed = timestamp(item['published_at']) <= cutoff
        item['cutoff_availability'] = 'published_by_cutoff' if allowed else 'hindsight'
        (admissible if allowed else hindsight).append(item)
    # Separate limits prevent later headlines crowding out contemporaneous discovery.
    admissible, hindsight = admissible[:limit], hindsight[:limit]
    return dict(items=admissible, admissible=admissible, hindsight=hindsight, cutoff=cutoff.isoformat(),
                as_of=str(as_of), role='discovery_candidates', sources=['pythia_archive', 'yahoo-finance'],
                availability=statuses, triage_status='deferred',
                notice='Discovery relevance is not evidential support. Investigate retrieves and assesses evidence independently.')


def admissible_headlines(feed, limit=12):
    """Bounded deterministic seam for future event triage; never a graph importer."""
    cutoff = timestamp(feed['cutoff'])
    return [i for i in feed['admissible'] if timestamp(i['published_at'], i.get('published_date_only', False)) <= cutoff][:min(limit, 12)]
