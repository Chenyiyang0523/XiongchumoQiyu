import copy
import pytest
from service.mock import action,effect,page
from service.models import TurnProposal
from storybook.engine import apply_operations,accept_proposal,replay,RuleError
from test_storybook import app,create,turn,operation


def at_last_allowed_page(app):
    story=create(app)
    for _ in range(6):story=turn(app,story)
    # The player deliberately delays fulfilling the return promise. The two
    # extra pages remain legitimate pages; neither invents closure.
    for _ in range(3):
        free=action('action.wait.'+str(story['state']['version']),'allocate','先多用一份时间','time',
                    [effect('resource','time',-1)],'又用一份时间核对，返回约定仍待兑现。')
        state,events=apply_operations(story,[],free_action=free)
        draft=TurnProposal.model_validate({'resolved_action':free,
            'page':page(len(story['pages'])+1,story['blueprint'],state,story['settings'],story['manifest'],story['events']+events)}).model_dump()
        story=accept_proposal(story,{'version':story['state']['version'],'operations':[],'text':'再核对一下','reason':''},draft)
        replay(story)
    assert len(story['pages'])==10 and story['status']=='active'
    return story


def test_last_allowed_page_can_execute_and_close_without_an_extra_page(app):
    story=at_last_allowed_page(app);before=copy.deepcopy(story)
    request={'version':story['state']['version'],'operations':[operation(story)],'text':'','reason':''}
    state,events=apply_operations(story,request['operations'])
    draft=TurnProposal.model_validate({'ending':{'title':'按约返回','text':'我们兑现了返回约定。','evidence':[events[-1]['id']],
                 'discoveries':state['knowledge'],'helped':['buddy'],'solution':'按核对好的路线返回。'}}).model_dump()
    completed=accept_proposal(story,request,draft)
    assert completed['status']=='complete' and len(completed['pages'])==10
    assert completed['state']['promises']['promise.return'] is True
    assert story==before
    replay(completed)


def test_unclosed_last_action_is_saved_as_continued_and_cannot_add_a_page(app):
    story=at_last_allowed_page(app)
    free=action('action.still.wait','allocate','先等等','time',[effect('resource','time',-1)],'等待花了一份时间，约定仍未完成。')
    request={'version':story['state']['version'],'operations':[],'text':'先等等','reason':''}
    draft=TurnProposal.model_validate({'resolved_action':free}).model_dump()
    continued=accept_proposal(story,request,draft)
    assert continued['status']=='continued' and len(continued['pages'])==10
    assert continued['state']['resources']['time']==story['state']['resources']['time']-1
    assert continued['state']['version']==story['state']['version']+1
    replay(continued)
    state,events=apply_operations(story,[],free_action=free)
    draft['page']=page(11,story['blueprint'],state,story['settings'],story['manifest'],story['events']+events)
    with pytest.raises(RuleError,match='page allowance'):accept_proposal(story,request,draft)
