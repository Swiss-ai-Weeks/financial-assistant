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
    with patch("pandas.read_csv", return_value=pd.DataFrame({"date":[], "ticker":[]})), \
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
    with patch("pandas.read_csv", return_value=pd.DataFrame({"date": [], "ticker": []})), \
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
