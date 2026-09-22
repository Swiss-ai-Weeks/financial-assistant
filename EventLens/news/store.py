"""SQLite news store: idempotent ingestion and strictly time-filtered retrieval."""
import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SCHEMA = '''CREATE TABLE IF NOT EXISTS articles (
 id TEXT PRIMARY KEY, ticker TEXT NOT NULL, title TEXT NOT NULL,
 summary TEXT NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL,
 published_at TEXT NOT NULL, ingested_at TEXT NOT NULL,
 UNIQUE(ticker,url)
); CREATE INDEX IF NOT EXISTS articles_ticker_time ON articles(ticker,published_at);'''


def normalize_ticker(ticker):
    """Normalize and validate a provider symbol without mapping it to a company."""
    if not isinstance(ticker, str):
        raise ValueError("Ticker must be a string")
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,15}", symbol):
        raise ValueError(f"Invalid ticker: {ticker!r}")
    return symbol


def utc_iso(value):
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('Timestamp must include a timezone (e.g. +00:00 or Z)')
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds')


def canonical_url(url):
    parsed = urlsplit(url.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('Article requires an HTTP(S) URL')
    query = urlencode([(k,v) for k,v in parse_qsl(parsed.query) if not k.lower().startswith('utm_')])
    return urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path.rstrip('/') or '/',query,''))


class NewsStore:
    def __init__(self, path='data/news.sqlite'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.execute('CREATE TABLE IF NOT EXISTS ingestion_days ('
                        'ticker TEXT NOT NULL, day TEXT NOT NULL, status TEXT NOT NULL, '
                        'article_count INTEGER NOT NULL, updated_at TEXT NOT NULL, '
                        'PRIMARY KEY(ticker,day))')
        self.db.commit()
        try:
            self.db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(id UNINDEXED, title, summary)')
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False

    def day_status(self, ticker, day):
        row = self.db.execute('SELECT status FROM ingestion_days WHERE ticker=? AND day=?',
                              (normalize_ticker(ticker), day)).fetchone()
        return row['status'] if row else None

    def mark_day(self, ticker, day, status, count):
        if status not in ('success', 'empty'):
            raise ValueError('Invalid ingestion status')
        with self.db:
            self.db.execute('INSERT INTO ingestion_days(ticker,day,status,article_count,updated_at) '
                            'VALUES (?,?,?,?,?) ON CONFLICT(ticker,day) DO UPDATE SET '
                            'status=excluded.status, article_count=excluded.article_count, updated_at=excluded.updated_at',
                            (normalize_ticker(ticker), day, status, count, utc_iso(datetime.now(timezone.utc))))

    def close(self):
        self.db.close()

    def add(self, ticker, articles):
        ticker = normalize_ticker(ticker)
        count = 0
        for item in articles:
            try:
                url = canonical_url(item['url'])
                title = str(item['title']).strip()
                published = utc_iso(item['published_at'])
                if not title:
                    continue
                article_id = hashlib.sha256(f'{ticker}|{url}'.encode()).hexdigest()
                with self.db:
                    cur = self.db.execute('INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?,?,?)',
                        (article_id,ticker,title,str(item.get('summary') or ''),str(item.get('source') or 'Unknown'),url,published,utc_iso(datetime.now(timezone.utc))))
                    if cur.rowcount:
                        count += 1
                        if self.fts:
                            self.db.execute('INSERT INTO articles_fts(id,title,summary) VALUES (?,?,?)',
                                (article_id,title,str(item.get('summary') or '')))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue  # Skip malformed provider records; never fabricate missing timestamps.
        return count

    def search(self, ticker, start_at, as_of_at, query='', limit=10):
        """Return only records with publication timestamps inside [start_at, as_of_at]."""
        start, cutoff = utc_iso(start_at), utc_iso(as_of_at)
        if start > cutoff:
            raise ValueError('start_at must not be later than as_of_at')
        limit = max(1, min(int(limit), 100))
        ticker = normalize_ticker(ticker)
        base = ('SELECT a.* FROM articles a WHERE a.ticker=? AND a.published_at>=? '
                'AND a.published_at<=?')
        params = [ticker,start,cutoff]
        if query.strip():
            tokens = re.findall(r'[\w]+',query,flags=re.UNICODE)
            if self.fts and tokens:
                base += ' AND a.id IN (SELECT id FROM articles_fts WHERE articles_fts MATCH ?)'
                params.append(' OR '.join('"'+token.replace('"','')+'"' for token in tokens[:12]))
            elif tokens:
                base += ' AND (' + ' OR '.join('(lower(a.title) LIKE ? OR lower(a.summary) LIKE ?)' for _ in tokens[:12]) + ')'
                for token in tokens[:12]:
                    params.extend([f'%{token.lower()}%',f'%{token.lower()}%'])
        base += ' ORDER BY a.published_at DESC, a.id LIMIT ?'
        params.append(limit)
        return [dict(row) for row in self.db.execute(base,params).fetchall()]
