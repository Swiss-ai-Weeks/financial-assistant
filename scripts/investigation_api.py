"""Synchronous investigation adapter for the existing anomaly HTTP server."""
from datetime import date, datetime, time, timezone
from pathlib import Path
from historical_api import selected_signal
from financial_assistant.simulation.pair_trade import simulate_pair_forward
import json
import os
from uuid import uuid4
from investigation_progress import progress_registry

from financial_assistant.anomaly_detection.cointegration import monitor_pairs
from financial_assistant.anomaly_detection.historical import HistoricalPairSignal
from financial_assistant.llm import OpenAICompatibleProvider
from investigate_historical_pair import investigate_signal, parse_aware_datetime


DEFAULT_MODELS = [{
    "provider": "nvidia-nim",
    "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "base_url": "http://127.0.0.1:8000/v1",
}]


def configured_models():
    models = json.loads(os.environ.get("CLAIMGRAPH_MODELS", json.dumps(DEFAULT_MODELS)))
    if not isinstance(models, list) or not models:
        raise ValueError("CLAIMGRAPH_MODELS must be a nonempty JSON list")
    for model in models:
        if any(not isinstance(model.get(key), str) or not model[key].strip()
               for key in ("provider", "model", "base_url")):
            raise ValueError("Each configured model needs provider, model and base_url")
    return models


def public_models():
    return {"models": [{key: item[key] for key in ("provider", "model")}
                       for item in configured_models()]}


def investigate(request, *, prices, fits, as_of, formation_observations):
    if not isinstance(request, dict):
        raise ValueError("Expected a JSON object")
    run_id = progress_registry.start(request.get("run_id"))
    def report(stage, message="", metrics=None):
        progress_registry.report(run_id, stage, message, metrics)
    try:
        result = _investigate(request, prices=prices, fits=fits, as_of=as_of,
                              formation_observations=formation_observations, report=report, run_id=run_id)
    except Exception:
        progress_registry.fail(run_id)
        raise
    report("complete")
    return result


def _investigate(request, *, prices, fits, as_of, formation_observations, report, run_id):
    selected = next((item for item in configured_models()
                     if item["provider"] == request.get("provider")
                     and item["model"] == request.get("model")), None)
    if selected is None:
        raise ValueError("Select a configured model/provider")
    historical = request.get("mode") == "historical"
    event_override = None
    if request.get('mode') in ('holding', 'research_pair'):
        from types import SimpleNamespace
        from financial_assistant.domain import AnomalyEvent
        from financial_assistant.portfolio.returns import validate_portfolio
        weights = validate_portfolio(request['portfolio'])
        ticker = request['ticker_a']
        peer = request.get('ticker_b') if request.get('mode') == 'research_pair' else None
        if request.get('mode') == 'holding' and ticker not in weights:
            raise ValueError('Holding is not in the supplied portfolio')
        observed_at = datetime.combine(date.fromisoformat(request['as_of']), time.max, timezone.utc)
        event_override = AnomalyEvent(anomaly_id=f'HOLDING-{uuid4()}', ticker=ticker,
            related_entities=(peer,) if peer else (), detected_at=observed_at, anomaly_type='human_research_request',
            summary=f'Human-requested research of {ticker}' + (f' / {peer}' if peer else ' portfolio holding'),
            metadata={'observed_at': observed_at.isoformat(), 'portfolio_weight': weights.get(ticker),
                      'interpretation': 'Prioritisation context; no anomaly or causal assertion'})
        signal = SimpleNamespace(as_of=observed_at.date(), anomaly=None,
                                 fit=SimpleNamespace(ticker_a=ticker, ticker_b=peer or ticker))
    elif historical:
        metadata, signal = selected_signal(request)
        observed_at = datetime.combine(date.fromisoformat(metadata['as_of']), time.max, timezone.utc)
    else:
        requested_date = date.fromisoformat(request["as_of"])
        if requested_date != as_of:
            raise ValueError("Candidate date differs from the current detector cache; run scan again")
        observed_at = parse_aware_datetime(request["observed_at"])
        if observed_at.date() != requested_date:
            raise ValueError("observed_at must fall on the candidate date in its stated timezone")
        pair = (request["ticker_a"], request["ticker_b"])
        fit = next((fit for fit in fits if (fit.ticker_a, fit.ticker_b) == pair), None)
        if fit is None:
            raise ValueError("Candidate pair is not in the current detector cache")
        entry = float(request.get("entry", 1.5))
        if not 0.5 <= entry <= 4:
            raise ValueError("entry must be between 0.5 and 4")
        _, anomalies = monitor_pairs(prices, (fit,), start=as_of, end=as_of, entry=entry)
        if not anomalies:
            raise ValueError("Candidate is no longer anomalous; run scan again")
        signal = HistoricalPairSignal(
            signal_id=f"LIVE-{uuid4()}", as_of=as_of, fit=fit, anomaly=anomalies[0],
            formation_observations=formation_observations,
            corr_min=fit.correlation, alpha=fit.pvalue, entry=entry,
        )
    progress_registry.cutoff(run_id, observed_at)
    provider = OpenAICompatibleProvider(
        provider_name=selected["provider"], model_name=selected["model"],
        base_url=selected["base_url"], max_tokens=2048,
    )
    from financial_assistant.portfolio.service import market_context, attach_market_graph
    from financial_assistant.portfolio.returns import analyze_portfolio, simulate_overlay
    research_context = {}
    if request.get('portfolio'):
        analysis = analyze_portfolio(prices, request['portfolio'], observed_at)
        research_context['portfolio'] = {k: v for k, v in analysis.items() if k != 'provenance'}
    if request.get('simulation') and request.get('portfolio') and signal.fit.ticker_a != signal.fit.ticker_b:
        simulation = simulate_overlay(prices, request['portfolio'],
            {'ticker_a': signal.fit.ticker_a, 'ticker_b': signal.fit.ticker_b}, observed_at,
            request['simulation'].get('gross_overlay', .02))
        research_context['simulation'] = {k: v for k, v in simulation.items() if k != 'provenance'}
    kwargs = {'event_override': event_override, 'research_context': research_context} if event_override or research_context else {}
    if hasattr(prices, 'columns'):
        kwargs['market_performance'] = market_context((signal.fit.ticker_a, signal.fit.ticker_b), observed_at, prices)
    graph, _bundle = investigate_signal(signal, observed_at=observed_at, provider=provider, progress=report, **kwargs)
    # Each execution gets a separate institutional review, even for the same pair/date.
    graph = graph.model_copy(update={"investigation_id": f"{graph.investigation_id}-{uuid4()}"})
    result = graph.model_dump(mode="json")
    attach_market_graph(result, market_context((signal.fit.ticker_a, signal.fit.ticker_b), observed_at, prices))
    if research_context:
        result['nodes'].append(dict(node_id=f'context:portfolio-{run_id}', kind='context',
            label='Portfolio research context (not admitted evidence)',
            data={'subtype': 'research_context', 'context': research_context}))
    if research_context.get('simulation', {}).get('status') == 'available':
        from financial_assistant.portfolio.service import attach_simulation_graph
        attach_simulation_graph(result, simulation, run_id)
        result['nodes'].append(dict(node_id=f'missing:simulation-{run_id}', kind='missing_evidence',
            label=research_context['simulation']['remaining_question'], data={'resolution_status': 'unresolved'}))
        for node in result['nodes']:
            if node['kind'] == 'hypothesis':
                result['edges'].append(dict(edge_id=f"{node['node_id']}-simulation-question", source=node['node_id'], target=f'missing:simulation-{run_id}', kind='requires', data={}))
    if historical:
        report("hindsight")
        # Reasoning is COMPLETE before the simulator can access future prices.
        try:
            outcome = simulate_pair_forward(signal, prices).model_dump(mode="json")
        except ValueError as exc:
            outcome = {"unavailable": str(exc)}
        result["historical"] = {**metadata, "observed_at": observed_at.isoformat(),
                                "signal": signal.model_dump(mode="json"), "case_type": "real_cached_market"}
        result["hindsight_outcome"] = outcome
        report("replay_save")
        directory = Path(".run/replays")
        directory.mkdir(parents=True, exist_ok=True)
        replay_id = str(uuid4())
        result["replay_id"] = replay_id
        temporary = directory / f"{replay_id}.tmp"
        temporary.write_text(json.dumps(result), encoding="utf-8")
        temporary.replace(directory / f"{replay_id}.json")
    return result


def investigate_missing_evidence(request):
    from missing_evidence_followup import FOLLOWUP_LOCK, run_followup
    if not FOLLOWUP_LOCK.acquire(blocking=False):
        raise ValueError('One follow-up investigation may run at a time')
    run_id = None
    try:
        selected = next((m for m in configured_models() if m['provider'] == request.get('provider')
                         and m['model'] == request.get('model')), None)
        if selected is None:
            raise ValueError('Select a configured model/provider')
        run_id = progress_registry.start(request.get('run_id'))
        graph = request['graph']
        anomaly = next(n['data'] for n in graph['nodes'] if n['kind'] == 'anomaly')
        cutoff = parse_aware_datetime(anomaly.get('metadata', {}).get('observed_at', anomaly['detected_at']))
        progress_registry.cutoff(run_id, cutoff)
        provider = OpenAICompatibleProvider(provider_name=selected['provider'], model_name=selected['model'],
                                            base_url=selected['base_url'], max_tokens=2048)
        result = run_followup(graph, request['requirement_id'], provider, run_id,
            lambda stage, message='', metrics=None: progress_registry.report(run_id, stage, message, metrics))
        # Save a new replay, retaining the original packet and all earlier execution records.
        directory = Path('.run/replays')
        directory.mkdir(parents=True, exist_ok=True)
        result['replay_id'] = str(uuid4())
        temporary = directory / f"{result['replay_id']}.tmp"
        temporary.write_text(json.dumps(result), encoding='utf-8')
        temporary.replace(directory / f"{result['replay_id']}.json")
        progress_registry.report(run_id, 'complete')
        return result
    except Exception:
        if run_id:
            progress_registry.fail(run_id)
        raise
    finally:
        FOLLOWUP_LOCK.release()
