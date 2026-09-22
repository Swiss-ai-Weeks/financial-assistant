"""Phase 1: fetch company news from Finnhub, then persist metadata and summaries."""
import json
import os
import time
import random
from urllib.error import HTTPError
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .store import NewsStore, normalize_ticker


def fetch_finnhub(ticker, start_date, end_date, api_key=None):
    ticker = normalize_ticker(ticker)
    key = api_key or os.environ.get('FINNHUB_API_KEY')
    if not key:
        raise RuntimeError('Set FINNHUB_API_KEY; never put your key in source code.')
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError('start_date must be <= end_date')
    url = 'https://finnhub.io/api/v1/company-news?' + urlencode(
        {'symbol':ticker,'from':start.isoformat(),'to':end.isoformat(),'token':key})
    request = Request(url,headers={'User-Agent':'FinancialAnomalyResearch/1.0'})
    with urlopen(request,timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload,list):
        raise RuntimeError('News provider returned an error or unexpected response; check API plan/rate limits.')
    records = []
    for item in payload:
        if not isinstance(item,dict) or not item.get('datetime'):
            continue
        published = datetime.fromtimestamp(item['datetime'],timezone.utc)
        if not (start <= published.date() <= end):
            continue  # Never store provider results outside the requested dates.
        records.append({'title':item.get('headline',''), 'summary':item.get('summary',''),
                        'source':item.get('source','Unknown'), 'url':item.get('url',''),
                        'published_at':datetime.fromtimestamp(item['datetime'],timezone.utc)})
    return records


def ingest_company_news(ticker,start_date,end_date,db_path='data/news.sqlite',api_key=None):
    ticker = normalize_ticker(ticker)
    articles = fetch_finnhub(ticker,start_date,end_date,api_key)
    store = NewsStore(db_path)
    try:
        inserted = store.add(ticker,articles)
        return {'ticker':ticker,'fetched':len(articles),'inserted':inserted,'database':str(store.path)}
    finally:
        store.close()


def ingest_anomaly_windows(anomalies_path='anomalies.json', db_path='data/news.sqlite',
                           days_before=7, api_key=None, request_interval=1.1, max_retries=3, max_wait=120, include_event_day=False):
    """Fetch each unique calendar day once, for the seven days BEFORE each anomaly.

    Daily granularity mitigates, but cannot eliminate, provider response truncation.
    The anomaly day is excluded because daily OHLCV cannot establish event ordering.
    """
    from pathlib import Path
    payload = json.loads(Path(anomalies_path).read_text(encoding='utf-8'))
    ticker = normalize_ticker(payload['ticker'])
    dates = sorted({date.fromisoformat(event['date']) for event in payload['events']})
    if not 1 <= days_before <= 30:
        raise ValueError('days_before must be between 1 and 30')
    needed_days = sorted({day - timedelta(days=offset)
                          for day in dates for offset in range(1, days_before + 1)})
    if include_event_day:
        needed_days = sorted(set(needed_days) | set(dates))
    store = NewsStore(db_path)
    fetched = inserted = empty_days = skipped_days = 0
    failures = []
    last_request = None
    try:
        for day in needed_days:
            day_string = day.isoformat()
            status = store.day_status(ticker, day_string)
            if status in ('success', 'empty'):
                skipped_days += 1
                print(f'{day}: SKIPPED (already recorded: {status})', flush=True)
                continue
            try:
                for attempt in range(max_retries + 1):
                    if last_request is not None:
                        wait = request_interval - (time.monotonic() - last_request)
                        if wait > 0:
                            time.sleep(wait)
                    last_request = time.monotonic()
                    try:
                        articles = fetch_finnhub(ticker, day_string, day_string, api_key)
                        break
                    except HTTPError as exc:
                        if exc.code != 429 or attempt >= max_retries:
                            raise
                        retry_after = exc.headers.get('Retry-After') if exc.headers else None
                        try:
                            delay = float(retry_after)
                        except (ValueError, TypeError):
                            delay = min(max_wait, 2 ** (attempt + 2) + random.uniform(0, 1))
                        delay = max(0, min(max_wait, delay))
                        print(f'{day}: HTTP 429; retry {attempt + 1}/{max_retries} after {delay:.1f}s', flush=True)
                        time.sleep(delay)
                count = store.add(ticker, articles)
                # Only mark a day complete AFTER its articles are persisted.
                store.mark_day(ticker, day_string, 'success' if articles else 'empty', len(articles))
                fetched += len(articles)
                inserted += count
                if not articles:
                    empty_days += 1
                print(f'{day}: fetched={len(articles)}; total_inserted={inserted}', flush=True)
            except HTTPError as exc:
                failures.append({'date':day_string, 'error':f'HTTP {exc.code}: {exc.reason}'})
                print(f'{day}: FAILED (HTTP {exc.code}: {exc.reason})', flush=True)
                if exc.code == 429:
                    print('Rate limit persists; stopping this run. Resume later with the same command.', flush=True)
                    break
            except Exception as exc:
                failures.append({'date':day_string,'error':str(exc)})
                print(f'{day}: FAILED ({type(exc).__name__}: {exc})',flush=True)
        return {'ticker':ticker,'anomalies':len(dates),'days_requested':len(needed_days),
                'empty_days':empty_days,'skipped_days':skipped_days,'fetched':fetched,'inserted':inserted,
                'failed_days':failures,'database':str(store.path),
                'note':'Zero results do not prove no news existed; API coverage and caps are unverified.'}
    finally:
        store.close()


def main(argv=None):
    """Explicit opt-in CLI; importing this module never fetches news."""
    import argparse
    parser = argparse.ArgumentParser(description='Ingest Finnhub news for any supported ticker.')
    parser.add_argument('--ticker', help='Provider ticker, e.g. a symbol from anomalies.json')
    parser.add_argument('--from-date', help='UTC start date YYYY-MM-DD')
    parser.add_argument('--to-date', help='UTC end date YYYY-MM-DD')
    parser.add_argument('--anomalies', help='Instead ingest days surrounding anomalies from this JSON file')
    parser.add_argument('--days-before', type=int, default=7)
    parser.add_argument('--include-event-day', action='store_true')
    parser.add_argument('--db', default='data/news.sqlite')
    parser.add_argument('--dry-run', action='store_true', help='Show intended date range without API requests or DB writes')
    args = parser.parse_args(argv)
    if args.anomalies:
        if args.ticker or args.from_date or args.to_date:
            parser.error('--anomalies cannot be combined with --ticker/--from-date/--to-date')
        from pathlib import Path
        payload = json.loads(Path(args.anomalies).read_text(encoding='utf-8'))
        ticker = normalize_ticker(payload['ticker'])
        dates = sorted({date.fromisoformat(e['date']) for e in payload['events']})
        if not 1 <= args.days_before <= 30:
            parser.error('--days-before must be between 1 and 30')
        needed = sorted({d - timedelta(days=n) for d in dates for n in range(1, args.days_before + 1)} |
                        (set(dates) if args.include_event_day else set()))
        if args.dry_run:
            print(json.dumps({'ticker': ticker, 'anomaly_count': len(dates),
                              'requested_days': len(needed), 'first_day': str(needed[0]) if needed else None,
                              'last_day': str(needed[-1]) if needed else None, 'database': args.db}, indent=2))
            return
        result = ingest_anomaly_windows(args.anomalies, args.db, args.days_before,
                                        include_event_day=args.include_event_day)
    else:
        if not all((args.ticker, args.from_date, args.to_date)):
            parser.error('Provide --ticker, --from-date and --to-date together, or --anomalies')
        ticker = normalize_ticker(args.ticker)
        start, end = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
        if start > end:
            parser.error('--from-date must not be later than --to-date')
        if args.dry_run:
            print(json.dumps({'ticker': ticker, 'from': str(start), 'to': str(end),
                              'database': args.db, 'requests': 1}, indent=2))
            return
        result = ingest_company_news(ticker, str(start), str(end), args.db)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
