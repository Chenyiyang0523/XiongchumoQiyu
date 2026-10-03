import copy
import json
from pathlib import Path

import pytest

from service import model_protocol as wire
from service.models import StoryBlueprint, BookPage, TurnProposal
from storybook.engine import initial_state, validate_page, effects, RuleError, accept_proposal, page_action_contexts
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
        'closure':old['closure'],'solution_tag':old['solution_tag'],'promises':old['promises'],
        'promise_descriptions':{key:'查明路线以后，与伙伴一起安全返回。' for key in old['promises']},
        'promise_goals':{key:{'knowledge':['clue.solution']} for key in old['promises']}}
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
    assert 'prop.footprint' not in p['illustration']['props']
    with pytest.raises(RuleError,match='hotspot object absent'):validate_page(p,state,b,m,[],list(m),'6-8')


def test_task_owner_requirement_cannot_be_replaced_by_finding_a_clue():
    b,state,m,settings,selected,model=world()
    model['tasks']=[wire.ModelTask(id='quest.recover',title='拿回地图',owners={'item.map':'player'}).model_dump()]
    b=StoryBlueprint.model_validate(wire.blueprint(model,settings,selected)).model_dump();state=initial_state(b,m)
    effects(state,{'verb':'observe','target':'clue.solution','effects':[{'op':'learn','target':'clue.solution','value':True}]},b,m,'knowledge')
    assert state['quests']['quest.recover']=='open'
    effects(state,{'verb':'observe','target':'item.map','effects':[{'op':'transfer','target':'item.map','value':'player'}]},b,m,'recovered')
    assert state['quests']['quest.recover']=='complete'


def test_model_can_place_a_real_owned_item_in_the_current_scene():
    b,state,m,*_=world();state['items']['item.map']['owner']='player'
    authored=wire.ModelAction(id='action.place',label='把地图铺在集合点',verb='use',target='item.map',
        give={'item.map':state['location']},feedback='地图铺在集合点，大家可以一起核对。').model_dump()
    compiled=wire.action(authored,state)
    effects(state,compiled,b,m,'placed')
    assert state['items']['item.map']['owner']=='scene.forest'


def test_model_cannot_place_an_item_at_a_remote_scene():
    b,state,m,*_=world();state['items']['item.map']['owner']='player'
    authored=wire.ModelAction(id='action.remote',label='把地图放在远处',verb='use',target='item.map',
        give={'item.map':'scene.bridge'},feedback='放置地图。').model_dump()
    before=copy.deepcopy(state)
    with pytest.raises(ValueError,match='unknown or ambiguous'):wire.action(authored,state)
    assert state==before


def test_consumed_item_diagnostic_identifies_the_immutable_instance():
    b,state,m,*_=world();state['items']['item.map']['owner']='consumed'
    action=wire.ModelAction(id='action.retake',label='取回地图',verb='observe',target='item.map',
        take=['item.map'],feedback='拿起地图。').model_dump()
    before=copy.deepcopy(state)
    with pytest.raises(ValueError,match='item already consumed: item.map'):wire.action(action,state)
    assert state==before


def test_page_can_travel_before_placing_an_item_but_cannot_place_remotely():
    b,state,m,*_=world();state['items']['item.map']['owner']='player'
    authored=opening(state,m)
    authored['interactions']=[
        wire.ModelInteraction(id='card.travel',kind='observe',instruction='带地图去小桥',actions=[
            wire.ModelAction(id='action.travel',label='去小桥',verb='move',target='scene.bridge',
                move={'player':'scene.bridge'},feedback='带着地图到达小桥。')]).model_dump(),
        wire.ModelInteraction(id='card.place',kind='items',instruction='把地图铺在桥边',actions=[
            wire.ModelAction(id='action.place',label='铺地图',verb='use',target='item.map',
                give={'item.map':'scene.bridge'},feedback='地图铺在桥边。')]).model_dump()]
    p=BookPage.model_validate(wire.page(authored,state,m)).model_dump()
    contexts=page_action_contexts(p,state,b,m)
    enabling=contexts['action.place'][0]
    assert enabling['location']=='scene.bridge'
    after=copy.deepcopy(enabling);effects(after,p['interactions'][1]['actions'][0],b,m,'place')
    assert after['items']['item.map']['owner']=='scene.bridge'
    with pytest.raises(RuleError,match='invalid recipient'):
        effects(copy.deepcopy(state),p['interactions'][1]['actions'][0],b,m,'remote')
    p['interactions']=p['interactions'][1:]
    with pytest.raises(RuleError,match='invalid recipient'):
        page_action_contexts(p,state,b,m)


def test_promise_flag_cannot_replace_actual_delivery_and_bad_goal_is_rejected():
    b,state,m,settings,selected,model=world()
    model['promise_goals']={'promise.return':{'owners':{'item.map':'npc.zhaolin'},'knowledge':[],'relationships':{}}}
    b=StoryBlueprint.model_validate(wire.blueprint(model,settings,selected)).model_dump();state=initial_state(b,m)
    state['items']['item.map']['owner']='player'
    flag=wire.ModelAction(id='action.empty.promise',label='说已经交还地图',verb='ask',target='npc.zhaolin',
        promises={'promise.return':True},feedback='说已经交还地图。').model_dump()
    with pytest.raises(RuleError,match='promise fulfilment facts missing'):effects(copy.deepcopy(state),wire.action(flag,state),b,m,'false.claim')
    assert state['promises']['promise.return'] is False and state['items']['item.map']['owner']=='player'
    flag['give']={'item.map':'npc.zhaolin'}
    effects(state,wire.action(flag,state),b,m,'real.delivery')
    assert state['items']['item.map']['owner']=='npc.zhaolin' and state['promises']['promise.return'] is True
    model['promise_goals']={}
    with pytest.raises(ValueError,match='typed factual goals'):wire.blueprint(model,settings,selected)

def test_take_then_move_compiles_in_physical_order_and_sprite_alias_is_exact():
    b,state,m,*_=world()
    state['items']['item.map']['owner']=state['location']
    a=wire.ModelAction(id='action.depart',label='拿地图去小桥',verb='move',target='scene.bridge',
        feedback='带上地图再出发',take=['item.map'],move={'player':'scene.bridge'}).model_dump()
    compiled=wire.action(a,state);effects(state,compiled,b,m,'departure')
    assert state['location']=='scene.bridge' and state['items']['item.map']['owner']=='player'
    state['characters']['npc.zhaolin']['location']='scene.bridge'
    authored=opening(state,m);authored['characters']['player']='character.xiongda.thinking'
    assert wire.page(authored,state,m)['illustration']['characters']['player']=='character.xiongda.thinking'
    authored['characters']['player']='character.xionger.thinking'
    with pytest.raises(ValueError,match='wrong character'):wire.page(authored,state,m)


def test_confirmed_hotspot_requests_its_physical_layer_without_inventing_ownership():
    b,state,m,*_=world();authored=opening(state,m)
    authored['items']=[]
    p=BookPage.model_validate(wire.page(authored,state,m)).model_dump()
    assert p['illustration']['props']==['prop.footprint']
    validate_page(p,state,b,m,[],list(m),'6-8')
    state['items']['item.footprint']['owner']='scene.cave'
    p=BookPage.model_validate(wire.page(authored,state,m)).model_dump()
    assert p['illustration']['props']==[]
    with pytest.raises(RuleError,match='hotspot object absent'):validate_page(p,state,b,m,[],list(m),'6-8')
