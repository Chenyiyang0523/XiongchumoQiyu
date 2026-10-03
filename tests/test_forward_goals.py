from copy import deepcopy

import pytest

from storybook.engine import blocked_goals, protect_goals, apply_operations, effects, validate_forward_page, RuleError
from test_model_protocol import world


def crafting_world():
    b,s,m,*_=world()
    s['items']['item.map']['owner']='player'
    s['items']['item.footprint']['owner']='player'
    s['items']['item.flag']={'id':'item.flag','name':'路旗','asset':'prop.flag','owner':'unmade',
        'recipe':['item.map','item.footprint']}
    b['promise_conditions']={'promise.return':[{'kind':'owner','key':'item.map','value':'npc.zhaolin'}]}
    craft={'id':'action.craft','label':'制作路旗','verb':'combine','target':'item.flag','inputs':['item.map','item.footprint'],
           'effects':[{'op':'craft','target':'item.flag','value':True}],'feedback':'制作路旗'}
    delivery={'id':'action.deliver','label':'交还地图','verb':'ask','target':'npc.zhaolin','effects':[
        {'op':'transfer','target':'item.map','value':'npc.zhaolin'},
        {'op':'promise','target':'promise.return','value':True},
        {'op':'transfer','target':'item.map','value':'player'}],'feedback':'伙伴核对地图后借回用于制作'}
    return b,s,m,craft,delivery


def test_consuming_promised_instance_is_rejected_without_changing_checkpoint():
    b,s,m,craft,_=crafting_world()
    story={'blueprint':b,'state':s,'manifest':m,'pages':[{'id':'page.1','interactions':[{'id':'card.craft','actions':[craft]}]}]}
    original=deepcopy(story)
    with pytest.raises(RuleError,match='irreversible action blocks unfinished goal'):
        apply_operations(story,[{'action_id':craft['id'],'items':craft['inputs']}])
    assert story==original


def test_fulfil_then_reuse_has_a_safe_page_sequence_and_actual_facts():
    b,s,m,craft,delivery=crafting_world()
    page={'interactions':[{'id':'card.delivery','actions':[delivery]},{'id':'card.craft','actions':[craft]}]}
    validate_forward_page(page,s,b,m)
    before=deepcopy(s);effects(s,delivery,b,m,'delivered');protect_goals(before,s,b)
    assert s['promises']['promise.return']
    before=deepcopy(s);effects(s,craft,b,m,'made');protect_goals(before,s,b)
    assert s['items']['item.map']['owner']=='consumed' and s['items']['item.flag']['owner']=='player'


def test_mutually_exclusive_card_cannot_hide_unsafe_consumption():
    b,s,m,craft,delivery=crafting_world()
    with pytest.raises(RuleError,match='irreversible action'):
        validate_forward_page({'interactions':[{'id':'card.either','actions':[delivery,craft]}]},s,b,m)


def test_required_recipes_cannot_consume_one_instance_twice_but_optional_can():
    b,s,m,_,_=crafting_world();b['promise_conditions']={};s['promises']['promise.return']=True
    s['items']['item.banner']={**s['items']['item.flag'],'id':'item.banner'}
    for k in ['flag','banner']:
        b['quests'].append({'id':'quest.'+k,'required':True,'dependencies':[],
            'conditions':[{'kind':'owner','key':'item.'+k,'value':'player'}]})
        s['quests']['quest.'+k]='open'
    assert {'quest.flag','quest.banner'}<=set(blocked_goals(s,b))
    b['quests'][-1]['required']=False
    assert not blocked_goals(s,b)


def test_prior_broken_history_is_not_rewritten_or_rejected_for_unrelated_progress():
    b,s,m,_,_=crafting_world();s['items']['item.map']['owner']='consumed'
    original=deepcopy(s);s['resources']['time']-=1
    protect_goals(original,s,b)
    assert blocked_goals(s,b)['promise.return'].endswith('item.map')
