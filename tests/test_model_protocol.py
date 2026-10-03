import copy
import json
from pathlib import Path

import pytest

from service import model_protocol as wire
from service.models import StoryBlueprint, BookPage, TurnProposal
from storybook.engine import initial_state, validate_page, effects, RuleError, accept_proposal
from service.mock import blueprint as fixture_blueprint


def world():
    manifest=json.loads(Path('game/storybook/asset_manifest.json').read_text(encoding='utf-8'))['assets']
    settings={'theme':'足迹','character':'熊大','age':'6-8','pages':8,'assets':list(manifest)}
    old=fixture_blueprint(settings,'mystery')
    selected={'arc':'mystery','cast':[c['name'] for c in old['characters']]}
    roles=wire.roles(settings,selected)
    authored={'title':old['title'],'goal':old['goal'],'conflict':old['conflict'],'scene':'scene.forest',
        'profiles':{cid:{k:next(c for c in old['characters'] if c['name']==name)[k] for k in ['motivation','strength','weakness']} for cid,name in roles.items()},
        'clues':old['clues'],'items':old['items'],'tasks':[{'id':'quest.route','title':'找到路线','knowledge':['clue.solution']}],
        'closure':old['closure'],'solution_tag':old['solution_tag'],'promises':old['promises']}
    model=wire.ModelBlueprint.model_validate(authored).model_dump()
    b=StoryBlueprint.model_validate(wire.blueprint(model,settings,selected)).model_dump()
    return b,initial_state(b,manifest),manifest,settings,selected,model


def opening(state,manifest):
    return wire.ModelPage.model_validate({'id':'page.1','title':'足迹分岔了',
        'text':'树林里传来轻轻的铃声，泥地上有两排不同的脚印。熊大停下脚步，请赵琳和自己一起看看：一条通往小桥，另一条绕向竹林。风掀起地图的一角，两个方向究竟哪一个更可靠呢？',
        'characters':{'player':'thinking','npc.zhaolin':'happy'},'items':['item.map','item.footprint'],
        'interactions':[{'id':'inter.1','kind':'observe','instruction':'发现不同的信息',
            'actions':[{'id':'action.trail','label':'看足迹','verb':'observe','target':'clue.trail','learn':['clue.trail'],'feedback':'知道足迹的方向','hotspot':'item.footprint'},
                       {'id':'action.sound','label':'听铃声','verb':'observe','target':'clue.sound','learn':['clue.sound'],'feedback':'知道铃声的方向'}]}]}).model_dump()


def test_identity_is_bound_to_selected_roles_and_facts_remain_model_authored():
    b,state,manifest,settings,selected,model=world()
    assert state['characters']['player']['name']=='熊大'
    assert state['characters']['npc.zhaolin']['name']=='赵琳'
    assert b['goal']==model['goal'] and b['clues']==model['clues']
    assert state['quests']['quest.route']=='open'
    bad=copy.deepcopy(model);bad['profiles']['invented']=bad['profiles']['player']
    with pytest.raises(ValueError):wire.blueprint(bad,settings,selected)


def test_compiled_page_keeps_physical_hotspots_and_counterfactual_consequences():
    b,state,m,*_=world();authored=opening(state,m);p=BookPage.model_validate(wire.page(authored,state,m)).model_dump()
    validate_page(p,state,b,m,[],list(m),'6-8')
    assert p['interactions'][0]['actions'][0]['hotspot']=='prop.footprint'
    a,z=p['interactions'][0]['actions'];s1,s2=copy.deepcopy(state),copy.deepcopy(state)
    effects(s1,a,b,m,'test.a');effects(s2,z,b,m,'test.z')
    assert s1['knowledge']!=s2['knowledge'] and state['knowledge']==[]


@pytest.mark.parametrize('amount',[0,-1,-12])
def test_resource_intention_cannot_create_resources(amount):
    b,state,m,*_=world()
    a=wire.ModelAction(id='action.spend',label='分配',verb='allocate',target='time',feedback='分配时间',spend={'time':amount}).model_dump()
    with pytest.raises(ValueError):wire.action(a,state)


def test_asset_binding_cannot_invent_expression_or_unavailable_item():
    b,state,m,*_=world();authored=opening(state,m)
    authored['characters']['player']='flying'
    with pytest.raises(ValueError):wire.page(authored,state,m)
    authored=opening(state,m);state['items']['item.footprint']['owner']='consumed'
    p=BookPage.model_validate(wire.page(authored,state,m)).model_dump()
    with pytest.raises(RuleError,match='inaccessible'):validate_page(p,state,b,m,[],list(m),'6-8')


def test_task_owner_requirement_cannot_be_replaced_by_finding_a_clue():
    b,state,m,settings,selected,model=world()
    model['tasks']=[wire.ModelTask(id='quest.recover',title='拿回地图',owners={'item.map':'player'}).model_dump()]
    b=StoryBlueprint.model_validate(wire.blueprint(model,settings,selected)).model_dump();state=initial_state(b,m)
    effects(state,{'verb':'observe','target':'clue.solution','effects':[{'op':'learn','target':'clue.solution','value':True}]},b,m,'knowledge')
    assert state['quests']['quest.recover']=='open'
    effects(state,{'verb':'observe','target':'item.map','effects':[{'op':'transfer','target':'item.map','value':'player'}]},b,m,'recovered')
    assert state['quests']['quest.recover']=='complete'
