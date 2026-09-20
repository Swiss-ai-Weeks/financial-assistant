"""Synchronous investigation adapter for the existing anomaly HTTP server."""
from datetime import date, datetime, time, timezone
from pathlib import Path
from historical_api import selected_signal
from financial_assistant.simulation.pair_trade import simulate_pair_forward
import json
import os
from uuid import uuid4

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
    selected = next((item for item in configured_models()
                     if item["provider"] == request.get("provider")
                     and item["model"] == request.get("model")), None)
    if selected is None:
        raise ValueError("Select a configured model/provider")
    historical = request.get("mode") == "historical"
    if historical:
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
    provider = OpenAICompatibleProvider(
        provider_name=selected["provider"], model_name=selected["model"],
        base_url=selected["base_url"], max_tokens=2048,
    )
    graph, _bundle = investigate_signal(signal, observed_at=observed_at, provider=provider)
    # Each execution gets a separate institutional review, even for the same pair/date.
    graph = graph.model_copy(update={"investigation_id": f"{graph.investigation_id}-{uuid4()}"})
    result = graph.model_dump(mode="json")
    if historical:
        # Reasoning is COMPLETE before the simulator can access future prices.
        try:
            outcome = simulate_pair_forward(signal, prices).model_dump(mode="json")
        except ValueError as exc:
            outcome = {"unavailable": str(exc)}
        result["historical"] = {**metadata, "observed_at": observed_at.isoformat(),
                                "signal": signal.model_dump(mode="json"), "case_type": "real_cached_market"}
        result["hindsight_outcome"] = outcome
        directory = Path(".run/replays")
        directory.mkdir(parents=True, exist_ok=True)
        replay_id = str(uuid4())
        result["replay_id"] = replay_id
        temporary = directory / f"{replay_id}.tmp"
        temporary.write_text(json.dumps(result), encoding="utf-8")
        temporary.replace(directory / f"{replay_id}.json")
    return result
