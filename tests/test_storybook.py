import copy
import json
import threading
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from service.app import create_app
from service.mock import MockProvider
from service.models import CreateRequest, SubmitRequest, TurnProposal
from service.provider import Provider, ModelError
from service.storage import Conflict, Store
from storybook.engine import apply_operations, accept_proposal, effects, initial_state, replay, RuleError, validate_page
from storybook.client import Library, ClientError
from storybook.export import export_html

@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path/'books.sqlite'), MockProvider(), False, 'test-guardian')

def create(app, theme='森林探险', age='6-8', pages=8):
    request = CreateRequest.model_validate({'settings': {'theme': theme, 'character': '熊大', 'age': age, 'pages': pages,
                          'assets': list(app.state.pipeline.manifest)}, 'idempotency_key': 'create-'+theme+age+str(pages)}).model_dump()
    jid = app.state.store.enqueue('test', 'create', request)
    app.state.pipeline.process(app.state.store.next_job())
    job = app.state.store.job(jid)
    assert job['phase'] == 'complete', job['error']
    return app.state.store.story(jid)

def operation(story, option=0):
    inter = story['pages'][-1]['interactions'][0]
    a = inter['actions'][option]
    op = {'action_id': a['id']}
    if a['verb'] == 'allocate':
        op['amount'] = -next(e['value'] for e in a['effects'] if e['op'] == 'resource')
    if inter.get('order_action') == a['id']:
        op['order'] = inter['order']
    return op

def turn(app, story, option=0, **kw):
    req = SubmitRequest.model_validate({'version': story['state']['version'], 'idempotency_key': 'turn-%s-%s' % (story['id'],story['state']['version']),
                'operations': [operation(story, option)], **kw}).model_dump()
    jid = app.state.store.enqueue('test', 'turn', req, story['id'])
    app.state.pipeline.process(app.state.store.next_job())
    job = app.state.store.job(jid)
    assert job['phase'] == 'complete', job['error']
    assert len(job['metrics']) <= 4
    return app.state.store.story(story['id'])

@pytest.mark.parametrize('theme', ['森林探险','寻宝之旅','拯救行动','友谊考验','竹林音乐会','小桥修理队'])
@pytest.mark.parametrize('age', ['6-8', '9-12'])
def test_complete_generic_books(app, theme, age):
    story = create(app, theme, age)
    for n in range(8):
        story = turn(app, story, n % 2 if len(story['pages'][-1]['interactions'][0]['actions']) > 1 else 0, reason='我们希望伙伴一起放心回家。')
        assert replay(story) == story['state']
    assert story['ending'] and story['status'] == 'complete'
    assert story['state']['quests']['quest.route'] == 'complete'
    assert story['state']['promises']['promise.return'] is True
    assert len({i['kind'] for p in story['pages'] for i in p['interactions']}) >= 3
    assert sum(bool(p['callbacks']) for p in story['pages']) >= 2
    assert all(p.get('discussion') == '我们希望伙伴一起放心回家。' for p in story['pages'])

@pytest.mark.parametrize('pages', [12,16,20])
def test_supported_lengths(app, pages):
    story = create(app,pages=pages)
    for n in range(pages):
        story = turn(app,story)
    assert len(story['pages']) == pages and story['ending']

def test_duplicate_and_stale_submission(app):
    story = create(app)
    req = SubmitRequest.model_validate({'version':1,'idempotency_key':'test-idempotency','operations':[operation(story)]}).model_dump()
    s = app.state.store
    jid = s.enqueue('test','turn',req,story['id'])
    assert s.enqueue('test','turn',req,story['id']) == jid
    with pytest.raises(Conflict):
        s.enqueue('test','turn',{**req,'reason':'different'},story['id'])
    app.state.pipeline.process(s.next_job())
    assert s.enqueue('test','turn',req,story['id']) == jid
    with pytest.raises(Conflict):
        s.enqueue('test','turn',{**req,'idempotency_key':'stale-key'},story['id'])
    assert s.story(story['id'])['state']['version'] == 2
    assert len(s.story(story['id'])['events']) == 1

def test_resource_and_ownership_rules(app):
    story=create(app)
    state=copy.deepcopy(story['state'])
    def check(action):
        with pytest.raises(RuleError):
            effects(copy.deepcopy(state),action,story['blueprint'],story['manifest'],'event.test')
    check({'verb':'use','target':'item.map','effects':[]})
    check({'verb':'allocate','target':'time','effects':[{'op':'resource','target':'time','value':-99}]})
    check({'verb':'allocate','target':'time','effects':[{'op':'resource','target':'time','value':4}]})
    check({'verb':'observe','target':'quest.route','effects':[{'op':'reward','target':'quest.route','value':True}]})
    state['characters']['buddy']['location']='scene.cave'
    check({'verb':'ask','target':'buddy','effects':[]})

def test_early_ending_missing_quest_and_unknown_asset(app):
    story=create(app)
    req={'version':1,'operations':[operation(story)],'text':'','reason':''}
    draft={'page':None,'events':[],'resolved_action':None,'clarification':[],
           'ending':{'title':'done','text':'done','evidence':['event.2.0'],'discoveries':[],'helped':[],'solution':'done'}}
    with pytest.raises(RuleError): accept_proposal(story,req,draft)
    page=copy.deepcopy(story['pages'][0]);page['illustration']['scene']='scene.unknown'
    with pytest.raises(RuleError): validate_page(page,story['state'],story['blueprint'],story['manifest'],[],story['settings']['assets'],'6-8')

def test_counterfactual_information_ownership_and_resource(app):
    story=create(app)
    s1,_=apply_operations(story,[operation(story,0)])
    s2,_=apply_operations(story,[operation(story,1)])
    assert s1['knowledge'] != s2['knowledge']
    for _ in range(3):story=turn(app,story)
    s1,_=apply_operations(story,[operation(story,0)]);s2,_=apply_operations(story,[operation(story,1)])
    assert s1['items']['item.map']['owner'] != s2['items']['item.map']['owner']
    story=turn(app,story);story=turn(app,story)
    s1,_=apply_operations(story,[operation(story,0)]);s2,_=apply_operations(story,[operation(story,1)])
    assert s1['resources']['time'] != s2['resources']['time']

def test_evidence_wrong_order_and_duplicate_reward(app):
    story=create(app)
    story=turn(app,story);story=turn(app,story)
    op=operation(story);op['order']=list(reversed(op['order']))
    with pytest.raises(RuleError):apply_operations(story,[op])
    story=turn(app,story);story=turn(app,story);story=turn(app,story)
    state=copy.deepcopy(story['state'])
    a={'verb':'observe','target':'quest.route','effects':[{'op':'reward','target':'quest.route','value':True}]}
    effects(state,a,story['blueprint'],story['manifest'],'event.reward')
    with pytest.raises(RuleError):effects(state,a,story['blueprint'],story['manifest'],'event.again')

@pytest.mark.parametrize('phase',['generating','reviewing','commit','response'])
def test_fault_preserves_action_and_atomicity(app,phase):
    story=create(app)
    fired=[]
    def fault(stage):
        if stage==phase and not fired:
            fired.append(stage);raise RuntimeError('injected')
    app.state.pipeline.fault=fault
    req=SubmitRequest.model_validate({'version':1,'idempotency_key':'fault-request','operations':[operation(story)]}).model_dump()
    jid=app.state.store.enqueue('test','turn',req,story['id'])
    app.state.pipeline.process(app.state.store.next_job())
    j=app.state.store.job(jid)
    current=app.state.store.story(story['id'])
    if phase=='response':
        assert j['phase']=='complete' and current['state']['version']==2
    else:
        assert j['phase']=='failed' and current==story and j['request']==req
        app.state.pipeline.fault=None
        app.state.store.retry(jid,'test')
        app.state.pipeline.process(app.state.store.next_job())
        assert app.state.store.story(story['id'])['state']['version']==2
    assert len(app.state.store.story(story['id'])['events'])==1

def test_restart_recovers_pending_job(app):
    story=create(app)
    req=SubmitRequest.model_validate({'version':1,'idempotency_key':'restart-request','operations':[operation(story)]}).model_dump()
    jid=app.state.store.enqueue('test','turn',req,story['id'])
    claimed=app.state.store.next_job();assert claimed['id']==jid
    fresh=Store(app.state.store.path);fresh.recover()
    app.state.pipeline.process(fresh.next_job())
    assert fresh.job(jid)['phase']=='complete'
    assert fresh.story(story['id'])['state']['version']==2

def test_free_negation_never_guessed_as_letter(app):
    story=create(app)
    req=SubmitRequest.model_validate({'version':1,'idempotency_key':'free-input-key','text':'我不去小桥，先询问伙伴，不把地图交给他。'}).model_dump()
    jid=app.state.store.enqueue('test','turn',req,story['id'])
    app.state.pipeline.process(app.state.store.next_job())
    job=app.state.store.job(jid)
    assert job['result']['clarification'] and job['phase']=='complete'
    assert app.state.store.story(story['id'])==story
    assert all(a['id'] not in {'A','B','C'} for a in job['result']['clarification'])
    choice=job['result']['clarification'][0]
    confirm=SubmitRequest.model_validate({'version':1,'idempotency_key':'confirm-understood','clarification_job':jid,'clarification_action':choice['id']}).model_dump()
    confirm_jid=app.state.store.enqueue('test','turn',confirm,story['id'])
    app.state.pipeline.process(app.state.store.next_job())
    assert app.state.store.job(confirm_jid)['phase']=='complete'
    assert app.state.store.story(story['id'])['state']['version']==2

def test_account_isolation_sessions_and_delete(app):
    client=TestClient(app)
    def auth(aid):
        session=client.post('/v2/sessions',json={'account_id':aid,'account_secret':'x'*32,'guardian_code':'test-guardian','consent':True})
        assert session.status_code==200
        return {'Authorization':'Bearer '+session.json()['access_token']}
    a=auth('account_abcdefghijkl');b=auth('account_mnopqrstuvwx')
    req={'settings':{'theme':'森林探险','character':'熊大','pages':8,'assets':list(app.state.pipeline.manifest)},'idempotency_key':'api-create-key'}
    jid=client.post('/v2/stories',json=req,headers=a).json()['job_id']
    app.state.pipeline.process(app.state.store.next_job())
    assert client.get('/v2/stories/'+jid,headers=b).status_code==404
    assert client.get('/v2/jobs/'+jid,headers=b).status_code==404
    assert client.delete('/v2/books/'+jid,headers=b).status_code==404
    assert client.get('/v2/stories/'+jid,headers=a).status_code==200
    assert client.delete('/v2/books/'+jid,headers=a).status_code==204
    assert client.get('/v2/stories/'+jid,headers=a).status_code==404

def test_library_export_and_immutable_read(app,tmp_path):
    story=create(app)
    for _ in range(8):story=turn(app,story)
    before=copy.deepcopy(story)
    a=Library(tmp_path,'account_abcdefghijkl');b=Library(tmp_path,'account_mnopqrstuvwx')
    a.save(story);assert a.load(story['id'])==story and not b.list()
    root=Path(__file__).resolve().parents[1]/'game'
    target=tmp_path/'offline.html'
    export_html(story,target,lambda p:(root/p).read_bytes())
    data=target.read_text()
    assert 'data:image/webp;base64,' in data and 'data:font/ttf;base64,' in data
    assert '<script src=' not in data
    assert story==before
    with pytest.raises(ClientError):a.load('../outside')
