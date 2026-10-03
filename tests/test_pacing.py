import copy
import json
from pathlib import Path
import pytest
from service.mock import blueprint
from service.pacing import frontier, progress, validate_resolution_page
from storybook.engine import initial_state, RuleError


def world():
    manifest=json.loads(Path('game/storybook/asset_manifest.json').read_text(encoding='utf-8'))['assets']
    b=blueprint({'theme':'路线','character':'熊大','age':'6-8','pages':12},'mystery')
    return b,initial_state(b,manifest),manifest


def test_completed_quests_do_not_hide_an_unfulfilled_promise():
    b,state,_=world()
    state['quests']={key:'complete' for key in state['quests']}
    b['promise_descriptions']={'promise.return':'核对路线后和伙伴一起返回集合点。'}
    demand=frontier(state,b)
    assert demand['unmet_conditions']==[]
    assert demand['unfulfilled_promises']==[{'id':'promise.return','description':b['promise_descriptions']['promise.return']}]


def test_late_filler_is_rejected_but_real_fulfilment_is_available():
    b,state,m=world();state['quests']={key:'complete' for key in state['quests']}
    filler={'id':'action.filler','verb':'ask','target':'buddy','effects':[{'op':'relationship','target':'buddy','value':1}]}
    page={'interactions':[{'id':'inter.filler','actions':[filler]}]}
    story={'status':'active','state':state,'blueprint':b,'manifest':m,'settings':{'pages':12},'pages':[{}]*10+[page]}
    context={'pace':'resolve','closure_readiness':{'ending_allowed':False,'interaction_types_used':['observe','items','dialogue']}}
    before=copy.deepcopy(story)
    with pytest.raises(RuleError,match='unfinished'):validate_resolution_page(story,context)
    assert story==before
    filler['effects'].append({'op':'promise','target':'promise.return','value':True})
    validate_resolution_page(story,context)
    assert state['promises']['promise.return'] is False


def test_required_optional_prerequisite_is_in_the_frontier():
    b,state,_=world()
    b['quests'].append({'id':'quest.pre','title':'得到许可','required':False,'dependencies':[],
                        'conditions':[{'kind':'relationship','key':'buddy','value':2,'comparison':'gte'}]})
    b['quests'][0]['dependencies']=['quest.pre'];state['quests']['quest.pre']='open'
    assert any(c['quest']=='quest.pre' for c in frontier(state,b)['unmet_conditions'])


def test_travelling_to_actual_holder_advances_ownership_prerequisite():
    b,state,_=world()
    b['quests']=[{'id':'quest.recover','title':'拿回地图','required':True,'dependencies':[],
                 'conditions':[{'kind':'owner','key':'item.map','value':'player'}]}]
    state['quests']={'quest.recover':'open'};state['items']['item.map']['owner']='scene.bridge'
    after=copy.deepcopy(state);after['location']='scene.bridge';after['characters']['player']['location']='scene.bridge'
    assert progress(state,after,b)>0
    after=copy.deepcopy(state);after['location']='scene.cave';after['characters']['player']['location']='scene.cave'
    assert progress(state,after,b)==0
