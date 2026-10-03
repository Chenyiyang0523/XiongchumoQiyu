import copy
import json

import pytest

from service.glm_provider import LocalGLMProvider
from service.prompts import compact_context


def test_generation_has_one_source_for_current_ownership_and_positions():
    raw={'story':{'blueprint':{'characters':[{'id':'player','name':'熊大','location':'scene.forest','knowledge':[],
              'motivation':'保护小桥','strength':'细心','weakness':'太操心'}],
              'items':[{'id':'item.map','owner':'scene.forest'}]},'state':{'location':'scene.forest'}},
         'post_action_state':{'location':'scene.bridge','characters':{'player':{'location':'scene.bridge'}},
               'items':{'item.map':{'owner':'player'}},'knowledge':[]},'action_events':[]}
    original=copy.deepcopy(raw);result=compact_context('proposal',raw)
    assert raw==original
    assert 'items' not in result['story']['blueprint'] and 'state' not in result['story']
    assert 'location' not in result['story']['blueprint']['characters'][0]
    assert result['post_action_state']['items']['item.map']['owner']=='player'
    assert result['next_action_constraints']['visible_items']==['item.map']


def test_review_uses_confirmed_preview_after_npc_events():
    raw={'story':{'blueprint':{'characters':[]}},'post_action_state':{'location':'scene.forest'},
         'confirmed_preview':{'state':{'location':'scene.bridge'},'page':{'state_snapshot':{'location':'scene.bridge'}}}}
    result=compact_context('review',raw)
    assert result['post_action_state']=={'location':'scene.bridge'}
    assert 'state' not in result['confirmed_preview'] and 'state_snapshot' not in result['confirmed_preview']['page']
    assert raw['post_action_state']['location']=='scene.forest'


def settings(tmp_path,monkeypatch,url='https://open.bigmodel.cn/api/anthropic'):
    p=tmp_path/'settings.json';p.write_text(json.dumps({'env':{'ANTHROPIC_BASE_URL':url,
       'ANTHROPIC_MODEL':'glm-5.3[1M]','ANTHROPIC_AUTH_TOKEN':'local-private-test'}},ensure_ascii=False),encoding='utf-8')
    monkeypatch.setenv('XCMQY_CLAUDE_SETTINGS',str(p))
    for key in ['XCMQY_LLM_ENDPOINT','XCMQY_LLM_MODEL','XCMQY_LLM_KEY','XCMQY_GLM_REASONING_EFFORT','XCMQY_GLM_REPAIR_EFFORT','XCMQY_MODEL_MAX_TOKENS']:
        monkeypatch.delenv(key,raising=False)


def test_glm_uses_supported_reasoning_and_exact_verified_coding_endpoint(tmp_path,monkeypatch):
    settings(tmp_path,monkeypatch);p=LocalGLMProvider()
    assert p.endpoint=='https://open.bigmodel.cn/api/coding/paas/v4/chat/completions'
    assert p.model=='glm-5.3' and p.max_tokens==20000
    assert p.payload_options('proposal')['thinking']=={'type':'enabled'}
    assert p.payload_options('review')['reasoning_effort']=='low'
    assert p.payload_options('repair')['reasoning_effort']=='high'
    assert 'local-private-test' not in json.dumps(p.payload_options('setup'))


def test_glm_refuses_unverified_host_or_unsupported_effort(tmp_path,monkeypatch):
    settings(tmp_path,monkeypatch,url='https://elsewhere.example/api/anthropic')
    with pytest.raises(ValueError,match='verified'):LocalGLMProvider()
    settings(tmp_path,monkeypatch);monkeypatch.setenv('XCMQY_GLM_REASONING_EFFORT','none')
    with pytest.raises(ValueError,match='effort'):LocalGLMProvider()
