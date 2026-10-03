import json
import httpx
import pytest
from service.provider import Provider, ModelError

@pytest.mark.parametrize('finish,content', [('length','{"approved":true}'),('content_filter','{}'),('stop','{"cut":'),(None,'{}')])
def test_truncated_or_malformed_response_is_rejected(monkeypatch,finish,content):
    monkeypatch.setenv('XCMQY_LLM_ENDPOINT','https://model.example/v1/chat/completions')
    monkeypatch.setenv('XCMQY_LLM_MODEL','test-model')
    real=httpx.Client
    transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'choices':[{'finish_reason':finish,'message':{'content':content}}],'usage':{'prompt_tokens':3,'completion_tokens':7}}))
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=transport,**kw))
    metrics=[]
    with pytest.raises(ModelError):Provider().call('review',{}, {},metrics.append)
    assert len(metrics)==1 and metrics[0]['success'] is False
    assert metrics[0]['input_tokens']==3 and metrics[0]['output_tokens']==7

def test_complete_structured_response(monkeypatch):
    monkeypatch.setenv('XCMQY_LLM_ENDPOINT','https://model.example/v1/chat/completions');monkeypatch.setenv('XCMQY_LLM_MODEL','test-model')
    real=httpx.Client
    transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"approved":true,"issues":[]}'}}]}))
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=transport,**kw))
    metrics=[]
    assert Provider().call('review',{}, {},metrics.append)['approved']
    assert metrics[0]['cost_usd'] is None
