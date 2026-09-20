"""The API adapter reuses detector state and the shared engine without live services."""
from datetime import date
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
api = importlib.import_module("investigation_api")


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.delenv("CLAIMGRAPH_MODELS", raising=False)
    fit = SimpleNamespace(ticker_a="GS", ticker_b="UAL", correlation=.8, pvalue=.02)
    prices = object()
    monitor = Mock(return_value=((), [object()]))
    monkeypatch.setattr(api, "monitor_pairs", monitor)
    signal = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(api, "HistoricalPairSignal", signal)
    graph = Mock(investigation_id="INV-GS-UAL")
    graph.model_copy.return_value.model_dump.return_value = {"nodes": [{"kind": "model_run"}], "edges": [{"kind": "produced_by"}]}
    engine = Mock(return_value=(graph, object()))
    monkeypatch.setattr(api, "investigate_signal", engine)
    request = {"ticker_a":"GS", "ticker_b":"UAL", "as_of":"2026-03-20",
               "observed_at":"2026-03-20T21:00:00+00:00", "entry":1.7,
               **api.public_models()["models"][0]}
    kwargs = dict(prices=prices, fits=[fit], as_of=date(2026, 3, 20), formation_observations=252)
    return request, kwargs, monitor, engine


def test_reuses_current_cache_and_selected_threshold(setup):
    request, kwargs, monitor, engine = setup
    result = api.investigate(request, **kwargs)
    monitor.assert_called_once_with(kwargs["prices"], tuple(kwargs["fits"]),
                                    start=kwargs["as_of"], end=kwargs["as_of"], entry=1.7)
    assert engine.call_args.kwargs["provider"].model_name == request["model"]
    assert engine.call_args.kwargs["observed_at"].utcoffset() is not None
    assert result["nodes"][0]["kind"] == "model_run"
    assert result["edges"][0]["kind"] == "produced_by"


def test_configured_alternative_provider(monkeypatch, setup):
    request, kwargs, _, engine = setup
    monkeypatch.setenv("CLAIMGRAPH_MODELS", '[{"provider":"other","model":"alternative","base_url":"http://localhost:9000/v1"}]')
    request.update(provider="other", model="alternative")
    api.investigate(request, **kwargs)
    provider = engine.call_args.kwargs["provider"]
    assert (provider.provider_name, provider.model_name) == ("other", "alternative")
    assert "base_url" not in api.public_models()["models"][0]


@pytest.mark.parametrize("patch", [
    {"observed_at":"2026-03-20T21:00:00"}, {"observed_at":"2026-03-21T21:00:00Z"},
    {"as_of":"2026-03-19"}, {"ticker_a":"UNKNOWN"}, {"model":"unconfigured"}, {"entry":0},
])
def test_rejects_invalid_request_before_engine(setup, patch):
    request, kwargs, _, engine = setup
    request.update(patch)
    with pytest.raises(ValueError):
        api.investigate(request, **kwargs)
    engine.assert_not_called()


def test_failure_is_propagated(setup):
    request, kwargs, _, engine = setup
    engine.side_effect = RuntimeError("Retrieval failed")
    with pytest.raises(RuntimeError, match="Retrieval failed"):
        api.investigate(request, **kwargs)


def test_http_route_returns_graph_and_error(monkeypatch, setup):
    """Exercise the real HTTP handler without loading unavailable market cache files."""
    import io
    import json
    import runpy
    from unittest.mock import patch
    import pandas as pd

    request, kwargs, _, _ = setup
    cache = {"fits":[], "as_of":"2026-03-20", "corr_floor":.5, "alpha_ceiling":.1, "formation_observations":252}
    with patch("pandas.read_csv", return_value=pd.DataFrame({"date":[], "ticker":[], "mapping_status":[]})), \
         patch.object(Path, "read_text", return_value=json.dumps(cache)):
        server = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/anomaly_api.py"))
    handler = object.__new__(server["Handler"])
    handler.path = "/api/investigations"
    handler.send_json = Mock()
    for side_effect in (None, RuntimeError("Inference failed")):
        raw = json.dumps(request).encode()
        handler.headers = {"Content-Length":str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        handler.do_POST.__globals__["investigate"] = Mock(return_value={"nodes":[], "edges":[]}, side_effect=side_effect)
        handler.do_POST()
        status, result = handler.send_json.call_args.args
        assert status == (400 if side_effect else 200)
        assert result == ({"error":"Inference failed"} if side_effect else {"nodes":[], "edges":[]})


@pytest.mark.parametrize("delivery_error", [BrokenPipeError, ConnectionResetError])
def test_completed_investigation_disconnect_never_sends_400(delivery_error):
    import io
    import json
    import runpy
    from unittest.mock import patch
    import pandas as pd

    cache = {"fits": [], "as_of": "2026-03-20", "corr_floor": .5,
             "alpha_ceiling": .1, "formation_observations": 252}
    with patch("pandas.read_csv", return_value=pd.DataFrame({"date": [], "ticker": [], "mapping_status": []})), \
         patch.object(Path, "read_text", return_value=json.dumps(cache)):
        server = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/anomaly_api.py"))
    handler = object.__new__(server["Handler"])
    handler.path = "/api/investigations"
    handler.headers = {"Content-Length": "2"}
    handler.rfile = io.BytesIO(b"{}")
    graph = {"nodes": [{"id": "completed"}], "edges": []}
    investigate = Mock(return_value=graph)
    handler.do_POST.__globals__["investigate"] = investigate
    handler.send_json = Mock(side_effect=delivery_error("disconnected"))
    handler.log_message = Mock()
    handler.do_POST()
    investigate.assert_called_once()
    handler.send_json.assert_called_once_with(200, graph)
    handler.log_message.assert_called_once()
    assert "completed but the client disconnected" in handler.log_message.call_args.args[0]


def test_progress_lifecycle_and_safe_failure(setup, monkeypatch):
    from investigation_progress import ProgressRegistry
    registry = ProgressRegistry()
    monkeypatch.setattr(api, "progress_registry", registry)
    request, kwargs, _, engine = setup
    request["run_id"] = "live-test"
    original = engine.return_value
    def execute(*args, progress, **kwargs):
        assert registry.get("live-test")["stage"] == "preparing"
        progress("research_plan", "secret prompt", {"research_tasks": 3, "text": "document body"})
        progress("retrieval", "secret token", {})
        progress("retrieval_complete", "", {"search_hits": 17, "BOOKREADER_API_TOKEN": "credential"})
        assert registry.get("live-test")["completed"] == ["preparing", "research_plan", "retrieval"]
        return original
    engine.side_effect = execute
    api.investigate(request, **kwargs)
    status = registry.get("live-test")
    assert status["state"] == "complete"
    assert status["metrics"] == {"research_tasks": 3, "search_hits": 17}
    assert not any(value in str(status) for value in ("secret", "credential", "document body", "BOOKREADER"))
    request["run_id"] = "failed-test"
    def fail(*args, progress, **kwargs):
        progress("research_plan", "", {"research_tasks": 2})
        progress("retrieval", "", {})
        raise RuntimeError("credential document body")
    engine.side_effect = fail
    with pytest.raises(RuntimeError, match="credential"):
        api.investigate(request, **kwargs)
    failed = registry.get("failed-test")
    assert failed["state"] == "failed"
    assert failed["stage"] == "retrieval"
    assert failed["completed"] == ["preparing", "research_plan"]
    assert "credential" not in str(failed)


def test_registry_concurrent_reads_and_bound():
    from concurrent.futures import ThreadPoolExecutor
    from investigation_progress import ProgressRegistry
    registry = ProgressRegistry(capacity=2)
    run = registry.start()
    def access(index):
        registry.report(run, "retrieval", metrics={"search_hits": index, "claims": "unsafe"})
        snapshot = registry.get(run)
        snapshot["completed"].append("corruption")
        snapshot["metrics"]["injected"] = "text"
        assert snapshot["state"] == "running"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(access, range(100)))
    assert "corruption" not in registry.get(run)["completed"]
    assert set(registry.get(run)["metrics"]) == {"search_hits"}
    registry.start("second")
    with pytest.raises(ValueError, match="Too many"):
        registry.start("third")
    registry.report(run, "complete")
    registry.start("third")
    assert registry.get(run) is None
    assert registry.get("unknown") is None


def test_status_http_unknown_and_known():
    import json
    import runpy
    from unittest.mock import patch
    import pandas as pd
    from investigation_progress import progress_registry
    cache = {"fits": [], "as_of": "2026-03-20", "corr_floor": .5,
             "alpha_ceiling": .1, "formation_observations": 252}
    with patch("pandas.read_csv", return_value=pd.DataFrame({"date": [], "ticker": [], "mapping_status": []})), \
         patch.object(Path, "read_text", return_value=json.dumps(cache)):
        server = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/anomaly_api.py"))
    handler = object.__new__(server["Handler"])
    handler.send_json = Mock()
    handler.path = "/api/investigations/status/unknown"
    handler.do_GET()
    assert handler.send_json.call_args.args[0] == 404
    run = progress_registry.start()
    handler.path = f"/api/investigations/status/{run}"
    handler.do_GET()
    assert handler.send_json.call_args.args == (200, progress_registry.get(run))
    progress_registry.report(run, "complete")


def test_real_pipeline_reports_order_at_execution_boundaries(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    import investigate_historical_pair as pipeline
    from datetime import datetime, timezone
    from test_pair_simulation import make_signal
    observed = datetime(2026, 1, 6, 23, 59, 59, 999999, timezone.utc)
    stages = []
    bundle = SimpleNamespace(hits=[1, 2], records=[], query_expansions=[])
    document = SimpleNamespace(document_id="doc", title="private body", publisher="publisher",
                               published_at=observed, url="url")
    claim = SimpleNamespace(text="private claim", document_id="doc", claim_type=SimpleNamespace(value="fact"))
    hypothesis = Mock(hypothesis_id="hypothesis", text="private hypothesis")
    hypothesis.model_copy.return_value = hypothesis
    def operation(expected, result):
        def execute(*args, **kwargs):
            assert stages[-1][0] == expected
            return result
        return execute
    for name in ("CorpusSearchProvider", "CorpusDocumentFetcher", "SearxngSearchProvider",
                 "TrafilaturaDocumentFetcher", "CompositeSearchProvider", "DispatchingDocumentFetcher"):
        monkeypatch.setattr(pipeline, name, Mock())
    monkeypatch.setattr(pipeline, "execute_research_plan", operation("retrieval", bundle))
    monkeypatch.setattr(pipeline, "select_historical_documents", lambda *a, **kw: (document,))
    monkeypatch.setattr(pipeline, "extract_document_claims",
                        operation("claim_extraction", ((document, object(), (claim,), None),)))
    monkeypatch.setattr(pipeline, "generate_hypotheses",
                        operation("hypothesis_generation", (object(), (hypothesis,))))
    monkeypatch.setattr(pipeline, "audit_hypotheses", operation("hypothesis_audit", (object(), (object(),))))
    monkeypatch.setattr(pipeline, "assess_relationships",
                        operation("relationship_assessment", ((object(),), (object(),))))
    monkeypatch.setattr(pipeline, "InvestigationState", lambda **kw: kw)
    monkeypatch.setattr(pipeline, "build_investigation_graph",
                        operation("graph_build", SimpleNamespace(nodes=[1, 2], edges=[1])))
    pipeline.investigate_signal(make_signal(), observed_at=observed, provider=object(),
                                progress=lambda *args: stages.append(args))
    assert [stage for stage, _, _ in stages] == [
        "preparing", "fundamentals", "fundamentals", "fundamentals_complete",
        "research_plan", "retrieval", "retrieval_complete", "evidence_selection",
        "claim_extraction", "claim_extraction_complete", "hypothesis_generation",
        "hypothesis_generation_complete", "hypothesis_audit", "hypothesis_audit_complete",
        "relationship_assessment", "relationship_assessment_complete", "graph_build", "graph_complete"]
    assert stages[-1][2] == {"nodes": 2, "edges": 1}
