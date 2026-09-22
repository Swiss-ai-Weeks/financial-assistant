"""Standalone news CLI. Does not modify the working financial agent."""
import argparse
import json
import random
from datetime import date
from pathlib import Path

from news.ingest import ingest_company_news, ingest_anomaly_windows
from news.retrieve import retrieve_evidence, format_context

from news.selection import select_events

# Demo is the default; --no-demo disables both date and count restrictions.
def select_demo_events(payload):
    return select_events(payload, demo=True)


def main():
    p = argparse.ArgumentParser(description='Phase 1 ingestion and Phase 2 local retrieval')
    p.add_argument('--db', default='data/news.sqlite')
    p.add_argument('--demo', action=argparse.BooleanOptionalAction, default=True)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('ingest'); a.add_argument('ticker'); a.add_argument('start_date'); a.add_argument('end_date')
    c = sub.add_parser('ingest-anomalies'); c.add_argument('--anomalies', default='anomalies.json'); c.add_argument('--days', type=int, default=7); c.add_argument('--include-event-day', action='store_true')
    b = sub.add_parser('search'); b.add_argument('ticker'); b.add_argument('start_at'); b.add_argument('as_of_at'); b.add_argument('--query', default=''); b.add_argument('--limit', type=int, default=10); b.add_argument('--context', action='store_true')
    i = sub.add_parser('investigate'); i.add_argument('--anomalies', default='anomalies.json'); i.add_argument('--days', type=int, default=7); i.add_argument('--output', default='news_investigation.txt')
    g = sub.add_parser('graph', help='Offline daily evidence graph using existing ranker; no LLM')
    g.add_argument('--anomalies', default='anomalies.json')
    g.add_argument('--date', required=True)
    g.add_argument('--days', type=int, default=7)
    g.add_argument('--semantic', help='Optional archived three-axis JSON for matching article IDs')
    g.add_argument('--output', default='evidence_graph.json')
    args = p.parse_args()
    if args.command == 'ingest':
        result = ingest_company_news(args.ticker, args.start_date, args.end_date, args.db)
    elif args.command == 'ingest-anomalies':
        if args.demo:
            payload = json.loads(Path(args.anomalies).read_text(encoding='utf-8'))
            selected = select_demo_events(payload)
            if not selected['events']:
                raise SystemExit('No anomalies in the last 365 days; no API requests sent.')
            # The existing ingestion function expects a path. A temporary JSON file
            # contains only the selected events; the original is never overwritten.
            import tempfile
            with tempfile.TemporaryDirectory() as folder:
                subset_path = Path(folder) / 'demo_anomalies.json'
                subset_path.write_text(json.dumps(selected), encoding='utf-8')
                print('DEMO selected anomalies:', [e['date'] for e in selected['events']], flush=True)
                result = ingest_anomaly_windows(str(subset_path), args.db, args.days, include_event_day=args.include_event_day)
        else:
            result = ingest_anomaly_windows(args.anomalies, args.db, args.days, include_event_day=args.include_event_day)
    elif args.command == 'graph':
        from news.evidence_graph import build_daily_evidence_graph, write_graph
        anomalies = json.loads(Path(args.anomalies).read_text(encoding='utf-8'))
        archived = json.loads(Path(args.semantic).read_text(encoding='utf-8')) if args.semantic else None
        result = build_daily_evidence_graph(anomalies, args.date, args.db, args.days, archived)
        write_graph(args.output, result)
        print(f"Evidence graph saved to {args.output}; groups={len(result['comparison'])}; "
              'LLM calls=0; causal ranks=0')
        return
    elif args.command == 'investigate':
        from news.investigate import investigate
        payload = json.loads(Path(args.anomalies).read_text(encoding='utf-8'))
        selected = select_events(payload, demo=args.demo)
        result = investigate(selected, args.db, args.days, args.output)
        print(f'Investigation saved to {args.output}')
        print(json.dumps({'ticker': result['ticker'], 'events': len(result['investigations'])}, indent=2))
        return
    else:
        result = retrieve_evidence(args.ticker, args.start_at, args.as_of_at, args.query, args.limit, args.db)
    print(format_context(result) if getattr(args, 'context', False) else json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
