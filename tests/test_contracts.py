import copy
from fastapi.testclient import TestClient
import pytest
from service.models import SubmitRequest, StoryRecord
from storybook.engine import RuleError, validate_page
from storybook.layout import rectangles
from test_storybook import app, create, turn, operation

def token(client):
    return client.post('/v2/sessions',json={'account_id':'test-account-0001','account_secret':'a'*32,'guardian_code':'test-guardian','consent':True}).json()['access_token']

def test_return_contract_and_pending_restore(app):
    with TestClient(app) as client:
        headers={'Authorization':'Bearer '+token(client)}
        story=create(app)
        with app.state.store.db() as db: db.execute("UPDATE stories SET account='test-account-0001'")
        req=SubmitRequest(version=1,idempotency_key='pending-recovery',operations=[operation(story)]).model_dump()
        jid=app.state.store.enqueue('test-account-0001','turn',req,story['id'])
        restored=client.get('/v2/stories/'+story['id'],headers=headers)
        assert restored.status_code==200
        assert restored.json()['pending']['request']==req
        StoryRecord.model_validate(restored.json())
        app.state.store.fail(jid,'injected')
        fresh={**req,'idempotency_key':'another-attempt'}
        other=app.state.store.enqueue('test-account-0001','turn',fresh,story['id'])
        app.state.pipeline.process(app.state.store.next_job())
        assert app.state.store.job(other)['phase']=='complete'
        assert client.get('/v2/stories/'+story['id'],headers=headers).json()['pending'] is None
        assert 'StoryRecord' in client.get('/openapi.json').json()['components']['schemas']

def test_invisible_hotspot_and_identical_choices_are_rejected(app):
    story=create(app); page=copy.deepcopy(story['pages'][0])
    args=(story['state'],story['blueprint'],story['manifest'],[],story['settings']['assets'],'6-8')
    page['interactions'][0]['actions'][0]['hotspot']='prop.bell'
    with pytest.raises(RuleError):validate_page(page,*args)
    page=copy.deepcopy(story['pages'][0]);a=copy.deepcopy(page['interactions'][0]['actions'][0]);a['id']='action.other';a['label']='换一种说法'
    page['interactions'][0]['actions']=[page['interactions'][0]['actions'][0],a]
    with pytest.raises(RuleError):validate_page(page,*args)

def test_six_props_and_four_characters_fit_canvas():
    art={'characters':{str(i):'character.'+str(i) for i in range(4)},'props':['prop.'+str(i) for i in range(6)]}
    manifest={a:{'scale':.75} for a in art['characters'].values()}
    actors,objects=rectangles(art,manifest)
    assert len(actors)==4 and len(objects)==6
    assert all(0<=x and x+w<=1 and 0<=y and y+h<=1 for _,x,y,w,h in actors+objects)

def test_entire_free_action_path_still_records_three_interaction_types(app):
    from service.mock import MockProvider
    class Free(MockProvider):
        def call(self,stage,context,schema,record):
            if stage not in {'proposal','repair'} or not context['request'].get('text'):return super().call(stage,context,schema,record)
            from storybook.engine import apply_operations
            action=context['story']['pages'][-1]['interactions'][0]['actions'][0]
            original=context['story']; preview={**original,'pages':original['pages'],'state':context['post_action_state']}
            state,events=apply_operations(preview,[],free_action=action)
            prepared={**context,'request':{**context['request'],'text':''},'post_action_state':state,'action_events':context['action_events']+events}
            result=super().call(stage,prepared,schema,record)
            result['resolved_action']=action
            return result
    story=create(app);app.state.pipeline.provider=Free()
    for n in range(8):
        req=SubmitRequest(version=story['state']['version'],idempotency_key='free-path-'+str(n),text='我的办法').model_dump()
        jid=app.state.store.enqueue('test','turn',req,story['id']);app.state.pipeline.process(app.state.store.next_job())
        assert app.state.store.job(jid)['phase']=='complete',app.state.store.job(jid)['error']
        story=app.state.store.story(story['id'])
    assert story['ending'] and len({e['interaction_kind'] for e in story['events']})>=3
