import copy

import pytest

from service.models import BookPage
from service.mock import action,effect
from storybook.engine import apply_operations, page_action_contexts, validate_page, RuleError, initial_state
from test_storybook import app,create


def workshop(app):
    story=create(app);state=story['state'];b=story['blueprint'];location=state['location']
    for iid,asset in [('item.wood','prop.plank'),('item.string','prop.rope')]:
        item={'id':iid,'name':iid,'asset':asset,'owner':location,'recipe':[]}
        b['items'].append(item);state['items'][iid]=copy.deepcopy(item)
    product={'id':'item.flag','name':'小旗','asset':'prop.flag','owner':'unmade','recipe':['item.wood','item.string']}
    b['items'].append(product);state['items'][product['id']]=copy.deepcopy(product)
    collect=action('action.collect','observe','收好木板和绳子','item.wood',[
        effect('transfer','item.wood','player'),effect('transfer','item.string','player')],'把材料收进背包')
    make=action('action.make','combine','组合成小旗','item.wood',[effect('craft','item.flag',True)],'做好了小旗')
    make['inputs']=['item.wood','item.string']
    p=copy.deepcopy(story['pages'][0]);p['illustration']['props']=['prop.plank','prop.rope']
    p.pop('state_snapshot',None)
    p['interactions']=[{'id':'inter.collect','kind':'observe','instruction':'先准备','actions':[collect]},
        {'id':'inter.make','kind':'items','instruction':'再组合','actions':[make]}]
    p=BookPage.model_validate(p).model_dump();p['state_snapshot']=copy.deepcopy(state);story['pages']=[p]
    return story


def test_collection_unlocks_crafting_on_same_page_without_changing_confirmed_state(app):
    story=workshop(app);before=copy.deepcopy(story['state']);page=story['pages'][0]
    validate_page(page,before,story['blueprint'],story['manifest'],[],story['settings']['assets'],'6-8')
    assert page_action_contexts(page,before,story['blueprint'],story['manifest'])['action.make']
    with pytest.raises(RuleError):apply_operations(story,[{'action_id':'action.make','items':['item.wood','item.string']}])
    state,events=apply_operations(story,[{'action_id':'action.collect'},
        {'action_id':'action.make','items':['item.wood','item.string']}])
    assert state['items']['item.flag']['owner']=='player'
    assert state['items']['item.wood']['owner']==state['items']['item.string']['owner']=='consumed'
    assert len(events)==2 and story['state']==before
    with pytest.raises(RuleError):apply_operations(story,[{'action_id':'action.make','items':['item.wood','item.string']},{'action_id':'action.collect'}])


def test_mutually_exclusive_options_cannot_unlock_each_other(app):
    story=workshop(app);page=story['pages'][0]
    page['interactions'][0]['actions'].append(page['interactions'][1]['actions'][0]);page['interactions'].pop()
    with pytest.raises(RuleError,match='item not owned'):
        validate_page(page,story['state'],story['blueprint'],story['manifest'],[],story['settings']['assets'],'6-8')

@pytest.mark.parametrize('condition',[
    {'kind':'owner','key':'item.map','value':'unknown-owner'},
    {'kind':'relationship','key':'buddy','value':20,'comparison':'gte'},
    {'kind':'resource','key':'time','value':999,'comparison':'gte'},
])
def test_impossible_core_conditions_are_rejected_before_opening(app,condition):
    story=create(app);b=copy.deepcopy(story['blueprint']);b['quests'][0]['conditions']=[condition]
    with pytest.raises(RuleError):initial_state(b,story['manifest'])
