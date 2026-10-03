import json

import httpx
import pytest

from service.anthropic_provider import ClaudeSettingsProvider, inline_schema, decode_typed_json
from service.models import StoryOpening
from service.provider import ModelError


def provider(monkeypatch,tmp_path,response):
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'env':{'ANTHROPIC_BASE_URL':'https://model.example/api/anthropic',
        'ANTHROPIC_MODEL':'glm-test[1M]','ANTHROPIC_AUTH_TOKEN':'private-local-token'}}))
    monkeypatch.setenv('XCMQY_CLAUDE_SETTINGS',str(path))
    for key in ['XCMQY_LLM_MODEL','XCMQY_LLM_KEY','XCMQY_LLM_ENDPOINT']:
        monkeypatch.delenv(key,raising=False)
    real=httpx.Client;requests=[]
    def respond(request):requests.append(request);return httpx.Response(200,json=response)
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    return ClaudeSettingsProvider(),requests


def result(**changes):
    return dict({'stop_reason':'tool_use','content':[{'type':'tool_use','name':'submit_story','input':{'approved':True,'issues':[]}}],
        'usage':{'input_tokens':11,'output_tokens':9,'cache_read_input_tokens':3}},**changes)


def test_protocol_uses_local_glm_configuration(monkeypatch,tmp_path):
    p,requests=provider(monkeypatch,tmp_path,result());metrics=[]
    assert p.call('review',{}, {'type':'object'},metrics.append)['approved'] is True
    request=requests[0];payload=json.loads(request.content)
    assert str(request.url)=='https://model.example/api/anthropic/v1/messages'
    assert payload['model']=='glm-test' and payload['tool_choice']['name']=='submit_story'
    assert request.headers['x-api-key']=='private-local-token'
    assert 'private-local-token' not in request.content.decode()
    assert metrics[0]['input_tokens']==14 and metrics[0]['output_tokens']==9
    assert metrics[0]['cost_usd'] is None


@pytest.mark.parametrize('response',[
    result(stop_reason='max_tokens'),result(stop_reason='end_turn'),
    result(content=[{'type':'tool_use','name':'Bash','input':{}}]),
    result(content=[{'type':'tool_use','name':'submit_story','input':{}},{'type':'tool_use','name':'submit_story','input':{}}]),
    result(content=[{'type':'tool_use','name':'submit_story','input':[]}]),
])
def test_truncation_and_unexpected_tools_are_rejected(monkeypatch,tmp_path,response):
    p,_=provider(monkeypatch,tmp_path,response);metrics=[]
    with pytest.raises(ModelError):p.call('review',{}, {'type':'object'},metrics.append)
    assert len(metrics)==1 and not metrics[0]['success']


def test_gateway_nested_json_is_decoded_without_changing_prose(monkeypatch,tmp_path):
    response=result(content=[{'type':'thinking','thinking':'not part of story'},
        {'type':'tool_use','name':'submit_story','input':{'nested':'{"id":"clue.real"}','text':'{"id":"unchanged prose"}'}}])
    p,_=provider(monkeypatch,tmp_path,response)
    schema={'type':'object','properties':{'nested':{'type':'object','properties':{'id':{'type':'string'}}},'text':{'type':'string'}}}
    value=p.call('proposal',{},schema,lambda _:None)
    assert value=={'nested':{'id':'clue.real'},'text':'{"id":"unchanged prose"}'}


def test_inline_schema_preserves_required_fields_and_limits():
    expanded=inline_schema(StoryOpening.model_json_schema())
    encoded=json.dumps(expanded)
    assert '$ref' not in encoded and '$defs' not in encoded
    blueprint=expanded['properties']['blueprint']
    assert 'arc' in blueprint['required'] and blueprint['additionalProperties'] is False
    assert expanded['properties']['page']['properties']['text']['maxLength']==260
    assert decode_typed_json('123',{'type':'string'})=='123'
