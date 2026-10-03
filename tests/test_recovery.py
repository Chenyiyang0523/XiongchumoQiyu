import copy
import json
import subprocess
from pathlib import Path
import pytest
from service.models import SubmitRequest
from service.mock import MockProvider
from service.provider import RetryableModelError
from storybook.engine import apply_operations, effects, replay, RuleError
from storybook.review import reflection, record_completion
from storybook.export import export_html
from test_storybook import app, create, turn, operation

def test_rate_limit_pauses_the_exact_action_without_content_repair(app):
    story=create(app);before=copy.deepcopy(story);stages=[]
    class Limited(MockProvider):
        def call(self,stage,context,schema,record):
            stages.append(stage)
            raise RetryableModelError('model HTTP 429; retry the preserved action later')
    app.state.pipeline.provider=Limited()
    request=SubmitRequest(version=story['state']['version'],idempotency_key='rate-limited-action',operations=[operation(story)]).model_dump()
    jid=app.state.store.enqueue('test','turn',request,story['id'])
    app.state.pipeline.process(app.state.store.next_job())
    job=app.state.store.job(jid)
    assert stages==['proposal'] and job['phase']=='failed' and 'HTTP 429' in job['error']
    assert job['request']==request and app.state.store.story(story['id'])==before

def test_crafting_is_atomic_and_replays(app):
    story=create(app)
    for _ in range(4):
        story=turn(app,story)
    for iid in ['item.paper','item.kite']:
        story['blueprint']['items'].append({'id':iid,'name':iid,'owner':'player' if iid=='item.paper' else 'unmade','asset':'prop.map','recipe':[] if iid=='item.paper' else ['item.paper','item.map']})
    story['initial_blueprint']=copy.deepcopy(story['blueprint'])
    from storybook.engine import initial_state
    base=initial_state(story['blueprint'],story['manifest'])
    for e in story['events']:
        effects(base,{'verb':'observe','target':'player','effects':e['effects']},story['blueprint'],story['manifest'],e['id'])
        base['version']=e['turn']
    story['state']=base
    action={'id':'action.craft','verb':'combine','target':'item.paper','label':'组合风筝','inputs':['item.paper','item.map'],
            'effects':[{'op':'craft','target':'item.kite','value':True}], 'feedback':'将纸与地图拼成风筝。'}
    story['pages'][-1]['interactions'][0]['actions']=[action]
    with pytest.raises(RuleError):
        apply_operations(story,[{'action_id':'action.craft','items':['item.paper']}])
    state,ev=apply_operations(story,[{'action_id':'action.craft','items':['item.paper','item.map']}])
    wrong=copy.deepcopy(action);wrong['inputs']=['item.paper']
    with pytest.raises(RuleError):effects(copy.deepcopy(story['state']),wrong,story['blueprint'],story['manifest'],'bad.recipe')
    assert state['items']['item.kite']['owner']=='player'
    assert all(state['items'][i]['owner']=='consumed' for i in action['inputs'])
    state['version']+=1
    story['state']=state;story['events']+=ev
    assert replay(story)==state
    with pytest.raises(RuleError):
        apply_operations(story,[{'action_id':'action.craft','items':action['inputs']}])

def test_review_repair_call_cap_and_failure_preserves_state(app):
    story=create(app)
    class Reject(MockProvider):
        def call(self,stage,context,schema,record):
            result=super().call(stage,context,schema,record)
            return {'approved':False,'issues':['事实矛盾']} if stage=='review' else result
    app.state.pipeline.provider=Reject()
    req=SubmitRequest.model_validate({'version':1,'idempotency_key':'reject-all','operations':[operation(story)]}).model_dump()
    jid=app.state.store.enqueue('test','turn',req,story['id'])
    app.state.pipeline.process(app.state.store.next_job())
    job=app.state.store.job(jid)
    assert job['phase']=='failed' and [m['stage'] for m in job['metrics']]==['proposal','review','repair','review']
    assert app.state.store.story(story['id'])==story and job['request']==req

def test_failed_calls_cannot_escape_book_budget(app,monkeypatch):
    story=create(app)
    monkeypatch.setenv('XCMQY_BOOK_CALL_LIMIT','5')
    class Invalid(MockProvider):
        def call(self,stage,context,schema,record):
            result=super().call(stage,context,schema,record)
            return {'bad':'schema'} if stage in {'proposal','repair'} else result
    app.state.pipeline.provider=Invalid()
    for n in range(2):
        req=SubmitRequest.model_validate({'version':1,'idempotency_key':'budget-attempt-'+str(n),'operations':[operation(story)]}).model_dump()
        jid=app.state.store.enqueue('test','turn',req,story['id'])
        app.state.pipeline.process(app.state.store.next_job())
        assert app.state.store.job(jid)['phase']=='failed'
    assert len(app.state.store.usage(story['id']))==5
    assert app.state.store.story(story['id'])==story

def test_snapshots_reflection_and_completion_are_consistent(app,tmp_path):
    story=create(app)
    first=copy.deepcopy(story['pages'][0]['state_snapshot'])
    for _ in range(8):story=turn(app,story,reason='为了伙伴安全返回。')
    assert story['pages'][0]['state_snapshot']==first
    assert first['knowledge']==[] and story['state']['knowledge']
    account={'play_stats':{'total_plays':0,'characters_used':[],'character_play_counts':{}}}
    assert record_completion(account,story) is True
    assert record_completion(account,story) is False
    assert account['play_stats']['total_plays']==1
    assert account['family_reviews_v2'][story['id']]['ending']==story['ending']
    assert all(a['reason']=='为了伙伴安全返回。' for a in reflection(story)['actions'])
    target=tmp_path/'book.html'
    export_html(story,target,lambda path:(Path('game')/path).read_bytes())
    script=target.read_text(encoding='utf-8').split('</script><script>')[1].split('</script>')[0]
    (tmp_path/'book.js').write_text(script, encoding='utf-8')
    # Parse actual exported JavaScript; do not merely assert that markup contains a title.
    result=subprocess.run(['node','--check',str(tmp_path/'book.js')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr

def test_free_allocation_uses_typed_quantity(app):
    story=create(app)
    a={'id':'action.custom','verb':'allocate','target':'time','effects':[{'op':'resource','target':'time','value':-2}], 'feedback':'花两份时间检查路线。','label':'先检查'}
    state,ev=apply_operations(story,[],free_action=a)
    assert state['resources']['time']==story['state']['resources']['time']-2
    assert ev[0]['verb']=='allocate'

def test_process_interruption_reserves_call_before_network(app,monkeypatch):
    story=create(app)
    class Interrupted(MockProvider):
        def call(self,*args): raise KeyboardInterrupt('process interrupted after send')
    app.state.pipeline.provider=Interrupted()
    req=SubmitRequest(version=1,idempotency_key='interrupted-call',operations=[operation(story)]).model_dump()
    jid=app.state.store.enqueue('test','turn',req,story['id'])
    with pytest.raises(KeyboardInterrupt):app.state.pipeline.process(app.state.store.next_job())
    assert app.state.store.job(jid)['metrics'][0]['interrupted'] is True
    assert len(app.state.store.usage(story['id']))==5
    monkeypatch.setenv('XCMQY_BOOK_CALL_LIMIT','5')
    app.state.store.recover();app.state.pipeline.provider=MockProvider()
    app.state.pipeline.process(app.state.store.next_job())
    assert app.state.store.job(jid)['phase']=='failed'
    assert app.state.store.story(story['id'])==story
