import copy
import io
import json
from unittest.mock import patch
import pytest
from financial_assistant.llm.model_registry import ModelConfig, registry, make_provider, guard_egress, available, RoutingError
from financial_assistant.llm.router import route_model
from financial_assistant.copilot.service import validate_reply, copilot


def model(**kw):
    return ModelConfig(provider='test', model='m', base_url='http://localhost:8000/v1', **kw)


def test_legacy_and_configuration(monkeypatch):
    monkeypatch.setenv('CLAIMGRAPH_MODELS', '[{"provider":"test","model":"m","base_url":"http://localhost:1/v1"}]')
    m = registry()[0]
    assert m.max_tokens == 8192 and m.roles == ['analysis'] and m.locality == 'local'
    assert not m.capabilities.no_think
    assert model(roles=['interaction'], capabilities={'no_think':True,'json_object':False}).capabilities.no_think
    for kw in ({'roles':['unknown']}, {'max_tokens':0}, {'capabilities':{'no_think':'yes'}}):
        with pytest.raises(ValueError): model(**kw)


@pytest.mark.parametrize('no_think', [True, False])
def test_completion_capabilities_auth_and_metadata(monkeypatch, no_think):
    monkeypatch.setenv('TEST_INFERENCE_KEY', 'secret-value')
    m = model(auth_env='TEST_INFERENCE_KEY', max_tokens=9876, capabilities={'no_think':no_think,'json_object':False})
    result = {'choices':[{'message':{'content':'{"answer":"ok"}'},'finish_reason':'stop'}], 'usage':{'prompt_tokens':7}}
    with patch('financial_assistant.llm.openai_compatible.urlopen', return_value=io.BytesIO(json.dumps(result).encode())) as call:
        provider = make_provider(m)
        assert provider.complete_json(system='system', user='user') == {'answer':'ok'}
    request = call.call_args.args[0]
    payload = json.loads(request.data)
    assert payload['messages'][0]['content'].startswith('/no_think') == no_think
    assert payload['max_tokens'] == 9876 and 'response_format' not in payload
    assert request.get_header('Authorization') == 'Bearer secret-value'
    assert provider.last_completion['prompt_tokens'] == 7
    assert provider.last_completion['finish_reason'] == 'stop'
    assert 'completion_tokens' not in provider.last_completion
    assert 'secret' not in json.dumps(m.public()) and 'auth_env' not in m.public()
    monkeypatch.delenv('TEST_INFERENCE_KEY')
    with pytest.raises(RoutingError, match='authentication'): provider.complete_json(system='',user='')


def test_routing_and_egress(monkeypatch):
    monkeypatch.delenv('CLAIMGRAPH_EGRESS_POLICY', raising=False)
    a = model(id='a'); b = model(id='b', roles=['interaction']); c = model(id='c', roles=['frontier'], locality='external')
    selected = {'provider':'test','model':'m','id':'a'}
    assert route_model([a,b,c], 'interaction', selected, health=lambda m:True) == b
    assert route_model([a,b,c], 'analysis', selected, health=lambda m:True) == a
    assert route_model([a,b,c], 'interaction', selected, health=lambda m:m.id == 'a') == a
    with pytest.raises(RoutingError, match='explicitly'): route_model([c], 'frontier', selected)
    with pytest.raises(RoutingError, match='blocked'): route_model([c], 'frontier', selected, explicit_frontier=True)
    with pytest.raises(RoutingError, match='unavailable'): route_model([a,b,c], 'interaction', selected, health=lambda m:False)
    monkeypatch.setenv('CLAIMGRAPH_EGRESS_POLICY','external_allowed')
    assert route_model([c], 'frontier', selected, explicit_frontier=True, health=lambda m:True) == c
    with patch('financial_assistant.llm.model_registry.urlopen', side_effect=OSError()): assert not available(b)


def test_action_validation():
    context = {'nodes':[{'id':'h'}], 'graph_summary':{'counts':{'hypothesis':1}}}
    for action in ({'type':'execute'}, {'type':'select_node','node_id':'unknown'}, {'type':'fit_graph','code':'evil'}, {'type':'fit_graph','kind':'https://example.com'}, {'type':'show_kind','kind':'unknown'}):
        with pytest.raises(ValueError): validate_reply({'answer':'ok','route':'interaction','ui_action':action},context,'interaction')
    assert validate_reply({'answer':'ok','route':'interaction','ui_action':{'type':'select_node','node_id':'h'}},context,'interaction')


def test_copilot_advisory_and_bounded(monkeypatch):
    context = {'nodes':[{'id':'h'}], 'workspace':{'id':'w'}}
    original = copy.deepcopy(context)
    provider = make_provider(model())
    provider.complete_json = lambda **kw: {'answer':'Explanation','route':'interaction','ui_action':None,'analysis_request':None}
    with patch('financial_assistant.copilot.service.route_model', return_value=model()), patch('financial_assistant.copilot.service.make_provider', return_value=provider):
        result = copilot({'question':'Explain','context':context})
    assert context == original and result['commentary'] and 'nodes' not in result
    with pytest.raises(ValueError, match='compact'): copilot({'question':'Explain','context':{'nodes':[], 'workspace':{'id':'x'*25000}}})


def test_route_intent_is_explicit():
    from financial_assistant.copilot.service import requested_route
    assert requested_route('Give me a frontier second opinion.') == ('frontier', True)
    assert requested_route('What is a frontier comparison?') == ('interaction', False)
    assert requested_route('Do not use frontier comparison.') == ('interaction', False)
    assert requested_route('Investigate this missing evidence.') == ('analysis', False)
    assert requested_route('What weakens this hypothesis?') == ('interaction', False)


def test_context_rejects_raw_state_and_nested_extras():
    from financial_assistant.copilot.context import validate_context
    for context in ({'nodes':[], 'html':'<body>'}, {'nodes':[{'id':'h','data':{'raw':{'arbitrary':True}}}]}, {'nodes':[{'id':str(i)} for i in range(31)]}):
        with pytest.raises(ValueError): validate_context(context)


def test_analysis_request_escalates_to_workspace_model(monkeypatch):
    a, b = model(id='a'), model(id='b', roles=['interaction'])
    providers = [make_provider(b, route='interaction'), make_provider(a, route='analysis')]
    providers[0].complete_json = lambda **kw: {'answer':'Needs assessment', 'route':'interaction', 'analysis_request':{'question':'Assess','target_node_id':'h'}}
    providers[1].complete_json = lambda **kw: {'answer':'Analysis commentary', 'route':'analysis'}
    with patch('financial_assistant.copilot.service.route_model', side_effect=[b,a]) as router, patch('financial_assistant.copilot.service.make_provider', side_effect=providers):
        result = copilot({'question':'Explain','context':{'nodes':[{'id':'h'}]}, 'analysis_model':a.public()})
    assert result['route'] == 'analysis' and result['model']['id'] == 'a'
    assert len(result['executions']) == 2
    assert router.call_args.args[1] == 'analysis'


def test_public_health_isolated(monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from investigation_api import public_models
    monkeypatch.setenv('CLAIMGRAPH_MODELS', json.dumps([model(id='a').model_dump(), model(id='b').model_dump()]))
    with patch('financial_assistant.llm.model_registry.available', side_effect=lambda m:m.id == 'a'):
        result = public_models(check_health=True)['models']
    assert [m['available'] for m in result] == [True,False]
    assert all('base_url' not in m and 'auth_env' not in m for m in result)


def test_selected_model_id_distinguishes_endpoints():
    from financial_assistant.llm.model_registry import resolve_model
    a, b = model(id='a'), model(id='b', max_tokens=4096)
    assert resolve_model([a,b], {'provider':'test','model':'m','model_id':'b'}) == b
    with pytest.raises(RoutingError, match='model ID'):
        resolve_model([a,b], {'provider':'test','model':'m'})


def test_egress_prevents_network_call(monkeypatch):
    monkeypatch.setenv('CLAIMGRAPH_EGRESS_POLICY','local_only')
    from financial_assistant.llm.openai_compatible import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(provider_name='test',model_name='m',base_url='https://example.com/v1')
    with patch('financial_assistant.llm.openai_compatible.urlopen') as network:
        with pytest.raises(RoutingError, match='blocked'):
            provider.complete_json(system='private',user='private')
    network.assert_not_called()


def test_concurrent_completion_metadata_is_isolated():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    provider = make_provider(model())
    barrier = Barrier(2)
    def record(tokens):
        provider.last_completion = {'completion_tokens':tokens}
        barrier.wait(timeout=3)
        return provider.last_completion['completion_tokens']
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(record,[10,20])) == [10,20]
