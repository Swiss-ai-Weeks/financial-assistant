"""Bounded enrichment orchestration and projection into existing domain objects."""
import csv
from datetime import datetime, timezone
from pathlib import Path
import re
from .metrics import DEFAULT_METRICS, REGISTRY, calculate, trends
from .models import FundamentalEvidenceBundle
from .normalize import normalize
from .provider import FundamentalsUnavailable, FundamentalsProvider


def sector_for(ticker):
    path = Path(__file__).resolve().parents[3] / 'data/universe/global_equities.csv'
    if path.exists():
        with path.open() as stream:
            sectors = {r['sector'] for r in csv.DictReader(stream) if r['yahoo_ticker'] == ticker and r['mapping_status'] == 'mapped'}
        if len(sectors) == 1:
            return sectors.pop()
    return None


class FundamentalsService:
    def __init__(self, provider: FundamentalsProvider):
        self.provider = provider

    def get_statement_history(self, ticker, as_of, periods=5, frequency='annual', *, _response=None):
        if not 1 <= periods <= (8 if frequency == 'quarterly' else 5):
            raise ValueError('periods must be between 1 and 8 for quarters, or 1 and 5 for years')
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError('as_of must include timezone')
        if frequency not in ('annual', 'quarterly'):
            raise ValueError('frequency must be annual or quarterly')
        if frequency == 'quarterly':
            return self.quarterly_metrics(ticker, as_of, periods=periods)
        response = _response or self.provider.get_company_facts(ticker, as_of)
        facts, warnings = normalize(response, as_of, frequency)
        ends = sorted({f.period_end for f in facts if f.period_start}, reverse=True)[:periods]
        # Extra prior year supports averages and YoY. It is later pruned to
        # the actual calculation lineage, never blindly graphed.
        prior = sorted({f.period_end for f in facts if f.period_start and (not ends or f.period_end < min(ends))}, reverse=True)[:4 if frequency == 'quarterly' else 1]
        starts = {f.period_start for f in facts if f.period_end in ends and f.period_start}
        from datetime import timedelta
        keep = set(ends + prior) | {s-timedelta(days=1) for s in starts}
        facts = tuple(f for f in facts if f.period_end in keep)
        selected_accessions = {f.accession for f in facts}
        recent = response.submissions.get('filings', {}).get('recent', {})
        filing_metadata = {}
        for i, accession in enumerate(recent.get('accessionNumber', [])):
            if accession in selected_accessions:
                filing_metadata[accession] = {key: recent[key][i] for key in
                    ('filingDate', 'reportDate', 'form', 'primaryDocument', 'acceptanceDateTime')
                    if isinstance(recent.get(key), list) and i < len(recent[key])}
        sector = sector_for(ticker)
        # SEC SIC is a conservative fallback, not a new classification engine.
        sic = str(response.submissions.get('sic', ''))
        financial = bool(sector and ('financial' in sector.lower() or 'bank' in sector.lower() or 'insurance' in sector.lower())) or (sic.isdigit() and 6000 <= int(sic) <= 6499)
        return FundamentalEvidenceBundle(ticker=ticker, issuer=response.facts.get('entityName', ''), cik=response.cik,
            as_of=as_of, periods=tuple(sorted(ends)), frequency=frequency, facts=facts, warnings=warnings if ends else (*warnings, 'No eligible statement durations available'),
            retrieved_at=response.retrieved_at, status='available' if ends else 'unavailable',
            provider_execution_metadata={**response.metadata, 'sector': sector, 'financial_institution': financial, 'selected_filing_metadata': filing_metadata,
                'classification_warning': 'Current universe/SEC classification used only to suppress unsuitable metrics; not historical evidence.',
                'operations': ['SEC fundamentals retrieval', 'point-in-time fact selection'],
                'availability_rule': 'filing date end-of-day UTC <= investigation cutoff'})

    def calculate_metrics(self, ticker, as_of, metrics=DEFAULT_METRICS, periods=5, frequency='annual', progress=None, *, _response=None):
        if set(metrics) - REGISTRY.keys():
            raise ValueError('Unknown metric requested')
        bundle = self.get_statement_history(ticker, as_of, periods, frequency, _response=_response)
        if frequency == 'quarterly':
            return bundle
        if progress:
            progress('financial_metrics', 'Calculating financial metrics')
        calculations = calculate(bundle.facts, bundle.periods, ticker=ticker, frequency=frequency, metrics=metrics,
                                 financial_institution=bundle.provider_execution_metadata['financial_institution'])
        if frequency == 'annual':
            calculations += trends(calculations, ticker)
        used = {fid for c in calculations if c.status == 'available' for fid in c.input_fact_ids}
        selected = {'revenue', 'operating_income', 'net_income', 'operating_cash_flow', 'cash'}
        facts = tuple(f for f in bundle.facts if f.fact_id in used or (f.period_end in bundle.periods and f.concept in selected))
        return bundle.model_copy(update={'facts': facts, 'calculations': calculations,
            'provider_execution_metadata': {**bundle.provider_execution_metadata,
                'operations': bundle.provider_execution_metadata['operations'] + ['deterministic metric calculation'],
                'selected_filing_metadata': {k: v for k, v in bundle.provider_execution_metadata['selected_filing_metadata'].items() if k in {f.accession for f in facts}},
                'fundamental_facts_selected': len(facts),
                'fundamental_metrics_calculated': sum(c.status == 'available' for c in calculations)}})


    def quarterly_metrics(self, ticker, as_of, progress=None, periods=8):
        from .quarterly import quarterly
        if not 1 <= periods <= 8 or as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError('Quarterly history requires 1–8 periods and a timezone-aware cutoff')
        # Preserve annual baseline calculations and their complete lineage.
        response = self.provider.get_company_facts(ticker, as_of)
        baseline = self.calculate_metrics(ticker, as_of, periods=3, progress=progress, _response=response)
        if baseline.provider_execution_metadata['financial_institution']:
            return baseline.model_copy(update={'frequency': 'quarterly', 'status': 'unavailable',
                'facts': (), 'calculations': (), 'periods': (),
                'warnings': ('Generic quarterly industrial accounting excluded for financial institutions.',)})
        snapshots, facts, calculations, warnings = quarterly(response, as_of, limit=periods)
        merged = {f.fact_id: f for f in (*baseline.facts, *facts)}
        recent = response.submissions.get('filings', {}).get('recent', {})
        accessions = {f.accession for f in merged.values()}
        filing_metadata = {accession: {key: recent[key][i] for key in
            ('filingDate', 'reportDate', 'form', 'primaryDocument', 'acceptanceDateTime')
            if isinstance(recent.get(key), list) and i < len(recent[key])}
            for i, accession in enumerate(recent.get('accessionNumber', [])) if accession in accessions}

        return baseline.model_copy(update={'frequency': 'quarterly', 'snapshots': snapshots,
            'periods': tuple(s.period_end for s in snapshots), 'facts': tuple(merged.values()),
            'calculations': (*baseline.calculations, *calculations),
            'status': 'available' if snapshots else 'unavailable',
            'provider_execution_metadata': {**baseline.provider_execution_metadata,
                'fundamental_facts_selected': len(merged),
                'fundamental_metrics_calculated': sum(c.status == 'available' for c in (*baseline.calculations, *calculations)),
                'quarterly_snapshots': len(snapshots), 'selected_filing_metadata': filing_metadata},
            'warnings': (*warnings, *(('No reliable fiscal quarter contexts; annual context only.',) if not snapshots else ()))})


def load_pair(tickers, as_of, *, service=None, progress=None):
    from .sec import SECProvider
    bundles = []
    for ticker in dict.fromkeys(tickers):
        try:
            if progress:
                progress('fundamentals', 'Loading historical fundamentals')
            active = service or FundamentalsService(SECProvider())
            bundles.append(active.quarterly_metrics(ticker, as_of, progress=progress))
        except (FundamentalsUnavailable, OSError, ValueError, KeyError, TypeError) as exc:
            # Exception bodies from transports are never sent to browsers/models.
            reason = str(exc) if isinstance(exc, FundamentalsUnavailable) else 'Fundamentals enrichment failed validation or retrieval'
            bundles.append(FundamentalEvidenceBundle(ticker=ticker, as_of=as_of, status='unavailable',
                warnings=(reason,), retrieved_at=datetime.now(timezone.utc),
                provider_execution_metadata={'operations': ['SEC fundamentals retrieval attempted'], 'status': 'unavailable'}))
    if progress:
        progress('fundamentals_complete', 'Fundamentals enrichment complete',
                 fundamental_facts_selected=sum(len(b.facts) for b in bundles),
                 fundamental_metrics_calculated=sum(c.status == 'available' for b in bundles for c in b.calculations))
    return tuple(bundles)


def model_context(bundles):
    import json
    records = []
    for b in bundles:
        items = {f.fact_id: f for f in b.facts}
        items.update({c.calculation_id: c for c in b.calculations})
        snapshots = []
        for s in b.snapshots:
            snapshots.append({'id': s.snapshot_id, 'fiscal_year': s.fiscal_year,
                'fiscal_quarter': s.fiscal_quarter, 'period_start': str(s.period_start),
                'period_end': str(s.period_end), 'available_at': s.available_at.isoformat() if s.available_at else None,
                'filings': s.filings,
                'metric_columns': ['metric', 'kind', 'provenance_id', 'value', 'unit'],
                'metrics': [[metric, 'observation' if identifier.startswith('SEC-') else 'calculation',
                    identifier, items[identifier].value, items[identifier].unit]
                    for metric, identifier in s.metrics.items()],
                'unavailable_metrics': list(s.unavailable_metrics),
                'unavailable_reason': 'No reliable eligible value or required calculation input; see graph for details'})
        records.append({'ticker': b.ticker, 'as_of': b.as_of.isoformat(), 'status': b.status,
            'warnings': b.warnings, 'quarterly_snapshots': snapshots,
            'trends': [{k: v for k, v in c.model_dump(mode='json').items() if k in
                        ('calculation_id', 'metric_id', 'value', 'unit', 'period_end', 'comparison_period',
                         'available_at', 'status', 'unavailable_reason')} for c in b.calculations
                       if c.frequency == 'quarterly' and b.periods and c.period_end == max(b.periods) and
                       ('_qoq_' in c.metric_id or '_yoy_' in c.metric_id)],
            'annual_baseline': [{'id': c.calculation_id, 'metric': c.metric_id, 'value': c.value,
                'period_end': str(c.period_end), 'status': c.status} for c in b.calculations
                if c.frequency == 'annual' and c.metric_id in DEFAULT_METRICS]})
    return ('Application-calculated financial evidence. Do not recompute metrics or invent values. '
        'Changes are descriptive, not causal. Interpret quarterly snapshots and deterministic trends first; '
        'annual_baseline is secondary context. Cite provenance IDs. Company differences do not establish an anomaly cause. '
        'Use patterns to request documentary evidence: management explanation, price versus volume, segments, '
        'inventory, receivables/payables, working capital, restructuring and guidance. '
        'Cash flow resilience does not prove a working-capital cause. Distinguish model inference, '
        'missing evidence and causal hypotheses from SEC observations and calculations.\n' + json.dumps(records, separators=(',', ':')))


def domain_evidence(bundles):
    from financial_assistant.domain import SourceDocument, Observation, Calculation
    documents, observations, calculations = {}, [], []
    for bundle in bundles:
        for fact in bundle.facts:
            if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', fact.accession) or not fact.cik.isdigit():
                raise ValueError('Invalid SEC filing identity')
            document_id = f'SEC-FILING-{fact.cik}-{fact.accession}'
            documents[document_id] = SourceDocument(document_id=document_id,
                title=f'{fact.ticker} {fact.form} filed {fact.filed_at}', publisher='SEC EDGAR',
                url=f'https://www.sec.gov/Archives/edgar/data/{int(fact.cik)}/{fact.accession.replace("-", "")}/{fact.accession}-index.html',
                published_at=fact.available_at, published_date_only=True, retrieved_at=fact.retrieved_at,
                text='Selected structured SEC Company Facts values; full filing text was not retrieved.',
                metadata={'form': fact.form, 'accession': fact.accession, 'filed_at': str(fact.filed_at), 'provider': fact.provider,
                          'submission': bundle.provider_execution_metadata.get('selected_filing_metadata', {}).get(fact.accession, {})})
            observations.append(Observation(observation_id=fact.fact_id,
                name=f'{fact.ticker} {fact.concept} period ending {fact.period_end}', value=fact.value, unit=fact.unit,
                source_document_id=document_id, metadata={**fact.model_dump(mode='json'),
                    'selection_as_of': bundle.as_of.isoformat(),
                    'historically_available': fact.available_at <= bundle.as_of,
                    'amended': fact.form.endswith('/A'),
                    'restatement_status': 'Selected latest eligible context; restatement not inferable from Company Facts alone',
                    'execution': 'SEC retrieval and deterministic point-in-time fact selection'}))
        fact_ids = {f.fact_id for f in bundle.facts}
        for result in bundle.calculations:
            if result.status != 'available':
                continue
            calculations.append(Calculation(calculation_id=result.calculation_id,
                label=f'{bundle.ticker} {result.display_name} period ending {result.period_end}', expression=result.formula,
                value=result.value, unit=result.unit,
                input_observation_ids=tuple(i for i in result.input_ids if i in fact_ids),
                input_calculation_ids=tuple(i for i in result.input_ids if i not in fact_ids),
                metadata={**result.model_dump(mode='json'), 'ticker': bundle.ticker,
                          'execution': 'deterministic application formula registry v1'}))
    return tuple(documents.values()), tuple(observations), tuple(calculations)
