"""Optional Pythia JSONL news archive as candidates in existing retrieval."""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .models import SearchHit


def archive_items(directory=None, *, ticker=None, as_of=None):
    root = Path(directory or os.environ.get('PYTHIA_NEWS_ARCHIVE', 'data/archive/news'))
    if ticker and not re.fullmatch(r'[A-Za-z0-9.^=_-]{1,30}', ticker):
        raise ValueError('Invalid ticker')
    paths = [root / f'{ticker.upper()}.jsonl'] if ticker else sorted(root.glob('*.jsonl'))
    limit = datetime.fromisoformat(str(as_of).replace('Z', '+00:00')) if as_of else datetime.now(timezone.utc)
    if limit.tzinfo is None:
        limit = limit.replace(tzinfo=timezone.utc)
        if len(str(as_of)) == 10:
            limit += timedelta(days=1) - timedelta(microseconds=1)
    unique = {}
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            try:
                item = json.loads(line)
                raw = item['published_at']
                stamp = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                date_only = len(raw) == 10 or item.get('published_date_only', False)
                if date_only:
                    stamp = datetime.combine(stamp.date(), datetime.max.time(), timezone.utc)
                if stamp.tzinfo is None or stamp > limit or not item.get('url', '').startswith(('http://', 'https://')):
                    continue
                item = {k: item.get(k) for k in ('news_id','ticker','title','summary','publisher','url','source')}
                if not item['news_id'] or not item['title']:
                    continue
                item.update(published_at=stamp.isoformat(), published_date_only=date_only,
                    role='retrieval_candidate', cutoff_availability='published_by_cutoff', archive_source=path.name)
                key = (re.sub(r'[^a-z0-9]', '', item['title'].lower()), stamp.date())
                unique.setdefault(key, item)
            except (ValueError, KeyError, TypeError):
                continue
    return sorted(unique.values(), key=lambda i: i['published_at'], reverse=True)


class ArchiveSearchProvider:
    name = 'pythia_archive'

    def __init__(self, directory=None):
        self.directory = directory

    def search(self, query, *, task_id, limit=5, as_of=None):
        words = set(re.findall(r'\w+', query.casefold()))
        ranked = []
        for item in archive_items(self.directory, as_of=as_of):
            title = set(re.findall(r'\w+', item['title'].casefold()))
            body = set(re.findall(r'\w+', (item.get('summary') or '').casefold()))
            score = 2 * len(words & title) + len(words & body)
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda x: (x[0], x[1]['published_at']), reverse=True)
        return tuple(SearchHit(hit_id=f"archive:{item['news_id']}", task_id=task_id,
            provider=self.name, query=query, rank=n, title=item['title'], url=item['url'],
            snippet=item.get('summary') or '', publisher=item.get('publisher'),
            published_at=item['published_at'], published_date_only=item['published_date_only'])
            for n, (_, item) in enumerate(ranked[:limit], 1))
