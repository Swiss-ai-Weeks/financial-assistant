"""Opt-in, read-only daily evidence map for the existing news pipeline.

No causal edges, invented market onset, new rank, or automatic acceptance of LLM claims.
Relies on the original ranker/grouping, not a duplicate scoring implementation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import html
import json
import sqlite3
import unicodedata

from .ranker import rank_articles
from .event_grouping import group_articles, rank_groups
from .investigate import _select_lanes, MAX_EVIDENCE


def _aware(value):
    obj = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if obj.tzinfo is None or obj.utcoffset() is None:
        raise ValueError('Timezone-aware timestamps required')
    return obj.astimezone(timezone.utc)


def _normalized(text):
    text = unicodedata.normalize('NFKC', html.unescape(str(text or '')))
    return ' '.join(text.translate(str.maketrans({'\u2018': "'", '\u2019': "'", '\u201c':'"', '\u201d':'"'})).split()).casefold()


def _semantic_annotation(row, article):
    """Archive is a model's *historical opinion*. Revalidate excerpts against current source."""
    if row is None:
        return {'status':'not_assessed', 'model_judgment':None, 'valid_citations':[], 'invalid_citations':[]}
    axes = row.get('semantic_axes') or {}
    valid, invalid = [], []
    for axis in ('event_verification','company_relationship','economic_mechanism'):
        judgement = axes.get(axis) or {}
        for citation in judgement.get('citations',[]):
            field=citation.get('field')
            quote=citation.get('quote')
            reference={'axis':axis,'article_id':citation.get('article_id'),'field':field,'quote':quote}
            if (citation.get('article_id')==article['id'] and field in ('title','summary')
                    and quote and _normalized(quote) in _normalized(article.get(field))):
                valid.append(reference)
            else:
                invalid.append(reference)
    return {'status':'archived_model_judgment_requires_review','model_judgment':{
                a:(axes.get(a) or {}).get('status') for a in ('event_verification','company_relationship','economic_mechanism')},
            'valid_citations':valid,'invalid_citations':invalid,
            'note':'Matching excerpt proves text presence, not claim entailment or causality.'}


def build_daily_evidence_graph(anomalies, anomaly_date, db_path='data/news.sqlite', days=7, semantic=None):
    """Build a provenance graph directly from local SQLite and the original ranker.

    No changes to anomalies, DB, baseline ranking code or reports.
    `semantic` optionally accepts archived Phase 5.2 JSON only when day/as-of match.
    """
    if not isinstance(days,int) or days<0 or days>365:
        raise ValueError('days must be between 0 and 365')
    day=date.fromisoformat(anomaly_date)
    matches=[e for e in anomalies['events'] if e.get('date')==anomaly_date]
    if len(matches)!=1:
        raise ValueError(f'Expected exactly one anomaly on {anomaly_date}; found {len(matches)}')
    ticker=anomalies['ticker'].strip().upper()
    if not ticker:raise ValueError('Missing ticker')
    local=ZoneInfo('America/New_York')
    start=datetime.combine(day-timedelta(days=days),time.min,local).astimezone(timezone.utc)
    cutoff=datetime.combine(day,time(16),local).astimezone(timezone.utc)
    if semantic is not None:
        # Fail closed: legacy archives without ticker cannot be proven to match.
        if str(semantic.get('ticker') or '').strip().upper() != ticker:
            raise ValueError('Semantic archive ticker missing or does not match anomaly ticker')
        if semantic.get('day')!=anomaly_date or _aware(semantic['as_of'])!=cutoff:
            raise ValueError('Semantic archive must match selected NY regular close and anomaly date')
        ids=[r['group_id'] for r in semantic.get('groups',[])]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate semantic archive IDs')
        archive={r['group_id']:r for r in semantic['groups']}
    else: archive={}
    path=Path(db_path)
    if not path.is_file():raise FileNotFoundError(f'News database does not exist: {path}')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        # Match original news/investigate.py window, but never mutate the live DB.
        articles=[dict(row) for row in db.execute(
            'SELECT id,ticker,title,summary,source,url,published_at,ingested_at FROM articles '
            'WHERE ticker=? AND published_at>=? AND published_at<=? ORDER BY published_at DESC,id LIMIT 5000',
            (ticker,start.isoformat(timespec='seconds'),cutoff.isoformat(timespec='seconds'))).fetchall()]
    articles=[a for a in articles if start<=_aware(a['published_at'])<=cutoff]
    ranked,relevant=rank_articles(articles,ticker,cutoff,len(articles),anomalies.get('company_name'),deduplicate=False)
    grouped=rank_groups(group_articles(ranked))
    selected,_=_select_lanes(grouped,max_evidence=MAX_EVIDENCE)
    anode=f'anomaly:{ticker}:{anomaly_date}'; cnode=f'company:{ticker}'
    event=matches[0]
    nodes={anode:{'id':anode,'type':'daily_anomaly','date':anomaly_date,
                  'return_pct':event.get('return_pct'),'volume_zscore':event.get('volume_zscore'),
                  'price_onset_at':None}, cnode:{'id':cnode,'type':'target_company','ticker':ticker}}
    edges=[{'source':anode,'target':cnode,'type':'observed_for_company',
            'provenance':'anomalies.json','causal':False}]
    rows=[]; article_groups=defaultdict(set)
    for position,group in enumerate(selected,1):
        representative=max(group,key=lambda a:(a['ranking']['score'],a['ranking']['event_specificity'],a['published_at']))
        group_id=representative['id']; eid=f'event_candidate:{group_id}'
        archived=archive.get(group_id)
        # The representative title is a retrieval proxy, NOT a model-verified event.
        archived_has_no_candidate = archived is not None and 'candidate_event' in archived and archived['candidate_event'] is None
        candidate = None if archived_has_no_candidate else ((archived or {}).get('candidate_event') or representative['title'])
        nodes[eid]={'id':eid,'type':('article_group_without_candidate' if archived_has_no_candidate else 'candidate_event_proxy'),
                    'title_proxy':candidate or representative['title'],
                    'candidate_validated':False,'group_id':group_id}
        edges.append({'source':eid,'target':anode,'type':'retrieved_for_daily_anomaly',
                      'provenance':group_id,'causal':False})
        items=[]; valid_quotes=[]; invalid_quotes=[]
        for a in group:
            aid='article:'+a['id']
            published=_aware(a['published_at'])
            if published>cutoff:raise ValueError('Post-cutoff article unexpectedly selected')
            classification='prior_day' if published.astimezone(local).date()<day else 'same_day_onset_unknown'
            annotation=_semantic_annotation(archived,a) if archived else _semantic_annotation(None,a)
            valid_quotes.extend(annotation['valid_citations']);invalid_quotes.extend(annotation['invalid_citations'])
            nodes[aid]={'id':aid,'type':'news_article','article_id':a['id'],
                        'title':a['title'],'published_at':a['published_at'],
                        'ingested_at':a.get('ingested_at'),'source_name':a.get('source'),
                        'source_url':a.get('url'),'daily_classification':classification,
                        'reporting_lineage_verified':False,'independent_confirmation_verified':False}
            edges.append({'source':aid,'target':eid,'type':'heuristically_grouped_with',
                          'provenance':a['id'],'semantic_entailment_verified':False,'causal':False})
            edges.append({'source':aid,'target':anode,'type':'daily_publication_context',
                          'provenance':a['id'],'classification':classification,
                          'relative_to_price_onset':'unknown','causal':False})
            article_groups[a['id']].add(group_id)
            items.append({'article_id':a['id'],'title':a['title'],'published_at':a['published_at'],
                          'classification':classification,'baseline_article_score':a['ranking']['score'],
                          'model_annotation':annotation})
        rows.append({'baseline_position':position,'group_id':group_id,'candidate_title_proxy':candidate or representative['title'],
                     'candidate_event':candidate, 'candidate_event_absent':archived_has_no_candidate,
                     'baseline_retrieval_score':representative['ranking']['score'],
                     'article_ids':[a['id'] for a in group],
                     'daily_classes':dict(Counter(a['classification'] for a in items)),
                     'archived_semantic_status':(archived or {}).get('status') if archived else None,
                     'archived_semantic_axes':(archived or {}).get('semantic_axes') if archived else None,
                     'valid_quote_matches':valid_quotes,'invalid_quote_matches':invalid_quotes,
                     'quote_match_is_not_entailment':True,'score_ready':False,
                     'graph_assisted_score':None,'new_rank':None,
                     'blockers':['intraday_price_onset_unknown','source_lineage_not_verified',
                                 'economic_mechanism_and_criteria_not_independently_validated'],
                     'articles':items})
    reused={a:sorted(gs) for a,gs in article_groups.items() if len(gs)>1}
    for row in rows:
        row['reused_articles_across_groups']=[a for a in row['article_ids'] if a in reused]
    assert all(e.get('causal') is False and e.get('provenance') for e in edges)
    return {'schema_version':'integrated_daily_evidence_graph_v1',
            'ticker':ticker,'anomaly_date':anomaly_date,'as_of':cutoff.isoformat(),
            'daily_anomaly':{'date':anomaly_date,'close':event.get('close'),
                             'return_pct':event.get('return_pct'),'volume_zscore':event.get('volume_zscore'),
                             'intraday_onset':None},
            'baseline_ranker_unchanged':True,'baseline_ranks_recomputed_by_original_ranker':True,
            'semantic_overlay_provided':semantic is not None,
            'stored_articles_in_window':len(articles),'lexically_relevant_articles':relevant,
            'model_calls':0,'trained_tgn':False,'graph_ranks_computed':0,
            'graph':{'nodes':list(nodes.values()),'edges':edges},
            'comparison':rows,'article_reuse_across_groups':reused,
            'limitations':['Offline SQLite only: no internet or model calls.',
                           'Publication-day context cannot establish news preceding price movement.',
                           'Ingestion after historical cutoff may imply retrospective rather than real-time availability.',
                           'Text-matched source excerpts do not verify semantic entailment or source independence.',
                           'No causal ranking or new economic scores; archived judgments remain unverified.']}


def format_markdown(data):
    def esc(value):return str(value).replace('|','\\|').replace('\n',' ')
    lines=[f"# Daily evidence map: {data['ticker']} {data['anomaly_date']}",
           f"As-of: {data['as_of']} · selected groups: {len(data['comparison'])} · model calls: 0",
           'Historical retrieval ranks from original news/ranker.py; no new scores or causal claims.', '',
           '| Position | Article/event title proxy | Prior-day | Same-day, onset unknown | Quotes matched | Review |',
           '|---:|---|---:|---:|---:|---|']
    for row in data['comparison']:
        count=row['daily_classes']
        review=row['archived_semantic_status'] or 'not assessed'
        if row['invalid_quote_matches']:review+='; rejected excerpt(s)'
        lines.append(f"| {row['baseline_position']} | {esc(row['candidate_title_proxy'])} | "
                     f"{count.get('prior_day',0)} | {count.get('same_day_onset_unknown',0)} | "
                     f"{len(row['valid_quote_matches'])} | {esc(review)} |")
    lines.extend(['','No model judgement or quote proves a stock-price cause. Market anomaly detector and original ranker remain unchanged.'])
    return '\n'.join(lines)+'\n'


def write_graph(path,data):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    target.with_suffix('.md').write_text(format_markdown(data),encoding='utf-8')
