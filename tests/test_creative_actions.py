import copy
import pytest
from service.models import TurnProposal
from service.mock import page
from storybook.engine import accept_proposal, replay, RuleError, apply_operations, expand_world
from test_storybook import app, create, operation

def creative_draft(story):
    expansion={'items':[{'id':'item.spare_map','name':'备用地图','owner':'scene.forest','asset':'prop.map','recipe':[]}],
               'clues':{'clue.spare':'备用地图上的折痕可以和旧地图比较。'},'quests':[]}
    action={'id':'action.custom_spare','verb':'observe','label':'先看看备用地图','target':'item.spare_map',
            'effects':[{'op':'transfer','target':'item.spare_map','value':'player'},{'op':'learn','target':'clue.spare','value':True},{'op':'learn','target':'clue.trail','value':True}],
            'feedback':'你发现备用地图，比较了折痕和足迹。','trait_use':{'character':'player','aspect':'strength','explanation':'仔细观察地图和足迹的联系。'}}
    preview=copy.deepcopy(story)
    expand_world(preview['state'],preview['blueprint'],expansion,preview['manifest'],'event.2.intro')
    state,events=apply_operations(preview,[],free_action=action)
    draft=TurnProposal(page=page(2,preview['blueprint'],state,story['settings'],story['manifest'],events),resolved_action=action,expansion=expansion).model_dump()
    return draft

def test_new_ideas_extend_ledger_without_rewriting_history(app):
    story=create(app);before=copy.deepcopy(story)
    result=accept_proposal(story,{'version':1,'operations':[],'text':'先比较备用地图','reason':'想确认折痕'},creative_draft(story))
    assert story==before
    assert 'clue.spare' not in result['initial_blueprint']['clues'] and 'clue.spare' in result['blueprint']['clues']
    assert result['state']['items']['item.spare_map']['owner']=='player'
    assert result['state']['provenance']['item:item.spare_map']=='event.2.0'
    assert result['events'][0]['expansion'] and result['events'][1]['interaction_kind']=='observe'
    assert result['pages'][0]['state_snapshot']==before['state']
    assert replay(result)==result['state']

@pytest.mark.parametrize('invalid',['owner','cycle','allocation_without_cost'])
def test_impossible_blueprint_or_resource_operation_is_rejected(app,invalid):
    from storybook.engine import initial_state, effects
    story=create(app);b=copy.deepcopy(story['blueprint'])
    if invalid=='allocation_without_cost':
        with pytest.raises(RuleError):effects(copy.deepcopy(story['state']),{'verb':'allocate','target':'time','effects':[{'op':'learn','target':'clue.trail','value':True}]},b,story['manifest'],'bad.allocation')
    else:
        if invalid=='owner':b['items'][0]['owner']='prop.map'
        else:
            b['items'][0]['recipe']=['item.loop'];b['items'].append({'id':'item.loop','name':'循环原料','owner':'player','asset':'prop.map','recipe':[b['items'][0]['id']]})
        with pytest.raises(RuleError):initial_state(b,story['manifest'])

@pytest.mark.parametrize('change',['old_clue','owned_item','new_required_quest'])
def test_expansion_cannot_override_or_grant_rewards(app,change):
    story=create(app);draft=creative_draft(story)
    if change=='old_clue':draft['expansion']['clues']['clue.trail']='旧足迹从未存在。'
    if change=='owned_item':draft['expansion']['items'][0]['owner']='player'
    if change=='new_required_quest':
        draft['expansion']['quests']=[{'id':'quest.surprise','title':'突然新增的必做事项','required':True,'dependencies':[],'conditions':[{'kind':'knowledge','key':'clue.spare','value':True}]}]
    with pytest.raises(RuleError):accept_proposal(story,{'version':1,'operations':[],'text':'检查','reason':''},draft)

def test_matching_free_action_is_accepted_but_cannot_overwrite_button(app):
    story=create(app);a=copy.deepcopy(story['pages'][0]['interactions'][0]['actions'][0])
    state,events=apply_operations(story,[],free_action=a)
    assert 'clue.trail' in state['knowledge'] and events[0]['interaction_kind']=='observe'
    a['effects']=[{'op':'learn','target':'clue.sound','value':True}]
    with pytest.raises(RuleError):apply_operations(story,[],free_action=a)

@pytest.mark.parametrize('change',['label','effects','duplicate'])
def test_clarification_cannot_disguise_a_different_action(app,change):
    story=create(app);before=copy.deepcopy(story)
    actions=copy.deepcopy(story['pages'][0]['interactions'][0]['actions'])
    if change=='label':actions[0]['label']='不查看足迹，先听铃声'
    elif change=='effects':actions[0]['effects']=[{'op':'learn','target':'clue.sound','value':True}]
    else:actions.append(copy.deepcopy(actions[0]))
    draft=TurnProposal(clarification=actions).model_dump()
    with pytest.raises(RuleError):accept_proposal(story,{'version':1,'text':'我不查看足迹','operations':[]},draft)
    assert story==before
