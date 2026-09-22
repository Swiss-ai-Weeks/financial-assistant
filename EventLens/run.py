"""Run the unchanged financial agent, then optionally ingest and investigate selected news."""
import argparse
import json
import tempfile
from pathlib import Path

from agent_runner import run_agent


def process_news(*, demo=True, db_path='data/news.sqlite', days=7,
                 investigate_news=True, output_dir='evidence', report_path='report.txt', validated=True):
    from news.selection import select_events
    from news.ingest import ingest_anomaly_windows
    from news.report_evidence import create_evidence_appendix
    from news.evidence_graph import format_markdown

    source = json.loads(Path('anomalies.json').read_text(encoding='utf-8'))
    selected = select_events(source, demo=demo)
    dates = [event['date'] for event in selected['events']]
    print(f'News mode: {"DEMO" if demo else "PRODUCTION"}; selected dates: {dates}', flush=True)
    if not dates:
        print('No eligible anomalies; no API requests sent.', flush=True)
        return
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    # One immutable selection for ingestion, investigation, and evidence graphs.
    with tempfile.TemporaryDirectory() as folder:
        subset = Path(folder) / 'selected_anomalies.json'
        subset.write_text(json.dumps(selected), encoding='utf-8')
        ingestion = ingest_anomaly_windows(str(subset), db_path, days_before=days,
                                           include_event_day=True)
    print('News ingestion:', ingestion, flush=True)
    if ingestion['failed_days']:
        print('News ingestion incomplete; skipping investigation and graphs.', flush=True)
        return
    investigation_path = output / 'news_investigation.txt'
    ranking_ready = False
    if investigate_news:
        from news.investigate import investigate
        print('Starting LLM news investigation (one call per selected news group)...', flush=True)
        old_scoring_mtime = (Path(str(investigation_path) + '.scores.json').stat().st_mtime_ns
                             if Path(str(investigation_path) + '.scores.json').exists() else None)
        investigate(selected, db_path=db_path, days=days,
                    output=str(investigation_path))
        if not investigation_path.is_file() or not investigation_path.read_text(encoding='utf-8').strip():
            raise RuntimeError('Investigation did not produce a nonempty output file')
        print(f'LLM investigation saved: {investigation_path}', flush=True)
        # Rank only the sidecar produced by this investigation. Never reuse stale scores.
        scoring_path = Path(str(investigation_path) + '.scores.json')
        if (not scoring_path.is_file() or
                scoring_path.stat().st_mtime_ns == old_scoring_mtime):
            print(f'Final ranking skipped: scoring sidecar missing: {scoring_path}', flush=True)
        else:
            from news.final_ranking import build_ranking, render_markdown
            try:
                scoring = json.loads(scoring_path.read_text(encoding='utf-8'))
                ranked = build_ranking(scoring)
                ranking_json = output / 'final_ranking.json'
                ranking_md = output / 'final_ranking.md'
                ranking_json.write_text(json.dumps(ranked, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                ranking_md.write_text(render_markdown(ranked), encoding='utf-8')
                ranking_ready = True
                print(f'Final ranking saved: {ranking_json}; {ranking_md}', flush=True)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                print(f'Final ranking skipped ({type(exc).__name__}: {exc}); investigation retained.', flush=True)
    # Graphs are offline and read-only. Each date gets a distinct filename.
    appendices = []
    for day in dates:
        result = create_evidence_appendix(anomaly_date=day, db_path=db_path,
                    graph_path=str(output / f'evidence_graph_{day}.json'),
                    combined_path=str(output / f'report_with_evidence_{day}.md'),
                    report_path=report_path)
        graph = json.loads(Path(result['graph_path']).read_text(encoding='utf-8'))
        appendices.append(format_markdown(graph))
    status = 'VALIDATED' if validated else 'UNVALIDATED DRAFT — requires review'
    combined = f'# Financial anomaly report ({status})\n\n' + Path(report_path).read_text(encoding='utf-8').rstrip()
    if investigate_news:
        combined += ('\n\n---\n\n# News investigation (LLM-reviewed; hypotheses are not proven causes)\n\n'
                     + investigation_path.read_text(encoding='utf-8').strip())
    else:
        combined += '\n\nNews investigation: skipped (--no-investigation).\n'
    if ranking_ready:
        combined += ('\n\n---\n\n# Final hypothesis ranking (unverified; audit-first)\n\n'
                     + ranking_md.read_text(encoding='utf-8').strip())
    combined += '\n\n---\n\n# Evidence appendices (descriptive, not causal)\n\n' + '\n\n---\n\n'.join(appendices)
    (output / 'report_with_evidence.md').write_text(combined + '\n', encoding='utf-8')
    if investigate_news:
        from news.clean_report import write_clean_report
        clean = write_clean_report(
            investigation_path=investigation_path,
            original_report_path=report_path,
            validated=validated,
            output_path=output / "report_clean.md",
            ranking_path=output / "final_ranking.json" if ranking_ready else None,
        )
        print(f'Readable report saved: {clean}', flush=True)
    print(f'Completed {len(dates)} selected anomalies; outputs in {output}/', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Financial anomaly agent')
    parser.add_argument('--demo', action=argparse.BooleanOptionalAction, default=True,
                        help='Demo: three random anomalies in the last 365 days (default); --no-demo: all')
    parser.add_argument('--no-news', action='store_true', help='Run original agent only')
    parser.add_argument('--no-investigation', action='store_true', help='Skip LLM investigation')
    parser.add_argument('--evidence-db', default='data/news.sqlite')
    args = parser.parse_args()
    report = Path('report.txt')
    draft = Path('report_draft.txt')
    before = {path: path.stat().st_mtime_ns if path.exists() else None
              for path in (report, draft)}
    run_agent(input('\nAsk the financial agent: '))
    if args.no_news:
        return
    # Only accept a report produced by THIS run; never reuse an old report.
    fresh_report = report.is_file() and report.stat().st_mtime_ns != before[report]
    fresh_draft = draft.is_file() and draft.stat().st_mtime_ns != before[draft]
    if fresh_report:
        source, validated = report, True
    elif fresh_draft:
        source, validated = draft, False
        print('News continuing from UNVALIDATED report_draft.txt; report.txt remains unchanged.', flush=True)
    else:
        print('News skipped: no fresh report or draft from this run.', flush=True)
        return
    if not source.read_text(encoding='utf-8').strip():
        print('News skipped: fresh report is empty.', flush=True)
        return
    try:
        process_news(demo=args.demo, db_path=args.evidence_db,
                     investigate_news=not args.no_investigation,
                     report_path=str(source), validated=validated)
    except Exception as exc:
        print(f'News pipeline failed ({type(exc).__name__}: {exc}). Main report.txt unchanged.', flush=True)


if __name__ == '__main__':
    main()
