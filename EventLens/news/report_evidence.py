"""Optional, offline evidence appendix. Never modifies the validated main report."""
from __future__ import annotations

import json
from pathlib import Path


def create_evidence_appendix(*, anomaly_date: str, anomalies_path: str = 'anomalies.json',
                             db_path: str = 'data/news.sqlite', semantic_path: str | None = None,
                             graph_path: str = 'evidence_graph.json',
                             report_path: str = 'report.txt',
                             combined_path: str = 'report_with_evidence.md') -> dict:
    """Create graph and companion report only after a validated report exists.

    The original report, anomaly JSON, database, ranker and detector are read-only here.
    This is descriptive evidence context, not causal validation or re-ranking.
    """
    from news.evidence_graph import build_daily_evidence_graph, format_markdown, write_graph

    main_report = Path(report_path)
    if not main_report.is_file() or not main_report.read_text(encoding='utf-8').strip():
        raise ValueError('A nonempty validated main report is required')
    anomalies = json.loads(Path(anomalies_path).read_text(encoding='utf-8'))
    semantic = (json.loads(Path(semantic_path).read_text(encoding='utf-8'))
                if semantic_path is not None else None)
    graph = build_daily_evidence_graph(anomalies, anomaly_date, db_path, semantic=semantic)
    # Validate the graph contract before any output is produced.
    if graph['graph_ranks_computed'] != 0 or any(
        row['new_rank'] is not None or row['graph_assisted_score'] is not None
        for row in graph['comparison']
    ):
        raise ValueError('Graph unexpectedly provided rankings or scores')
    appendix = format_markdown(graph)
    # Never overwrite the main report or a source input with an output path.
    inputs = {main_report.resolve(), Path(anomalies_path).resolve(), Path(db_path).resolve()}
    if semantic_path is not None:
        inputs.add(Path(semantic_path).resolve())
    outputs = [Path(graph_path), Path(graph_path).with_suffix('.md'), Path(combined_path)]
    if len({p.resolve() for p in outputs}) != len(outputs) or any(p.resolve() in inputs for p in outputs):
        raise ValueError('Output paths must be distinct and must not overwrite inputs')
    combined = ('# Financial anomaly report\n\n' + main_report.read_text(encoding='utf-8').rstrip()
                + '\n\n---\n\n# Evidence appendix (descriptive; not causal)\n\n'
                + appendix)
    write_graph(graph_path, graph)
    target = Path(combined_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(combined, encoding='utf-8')
    return {'graph_path': str(graph_path), 'graph_markdown_path': str(Path(graph_path).with_suffix('.md')),
            'combined_path': str(target), 'groups': len(graph['comparison'])}
