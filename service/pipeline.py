import json
import os
import secrets
import threading
from pydantic import ValidationError
from copy import deepcopy
from pathlib import Path
from service.models import Concepts, StoryBlueprint, StoryOpening, BookPage, TurnProposal, Review, StoryRecord
from service.provider import BudgetExceeded, ModelError
from service.context import for_generation, review_preview
from service.prompts import compact_context
from service import model_protocol
from storybook.engine import initial_state, validate_page, apply_operations, accept_proposal, replay, RuleError, effects, page_action_contexts

MANIFEST_PATH = Path(__file__).resolve().parents[1] / 'game/storybook/asset_manifest.json'

def page_diagnostics(page, state, blueprint, manifest, event_ids, settings):
    """Return independent hard errors together so the single repair can fix them."""
    errors=[]
    if not page:return errors
    try:contexts=page_action_contexts(page,state,blueprint,manifest,require_all=False)
    except ValueError:contexts={}
    for inter in page['interactions']:
        outcomes={}
        for action in inter['actions']:
            trial={**page,'interactions':[{**inter,'actions':[action],'order':[],'order_action':None}]}
            enabling=(contexts.get(action['id']) or [state])[0]
            # Only effects use the enabling state. Static page artwork remains
            # anchored to the confirmed page, including its original scene.
            try:effects(deepcopy(enabling),action,blueprint,manifest,'diagnostic')
            except ValueError as exc:errors.append(action['id']+': '+str(exc))
            else:
                after=deepcopy(enabling);effects(after,action,blueprint,manifest,'diagnostic')
                signature=json.dumps({k:v for k,v in after.items() if k!='provenance'},sort_keys=True)
                if signature in outcomes:
                    errors.append(outcomes[signature]+' and '+action['id']+': identical state outcomes; different wording/trait explanation is not a consequence. Change an actual knowledge/item/resource/relationship outcome.')
                else:outcomes[signature]=action['id']
    return list(dict.fromkeys(errors))[:12]

def fingerprint(story):
    b = story['blueprint']
    return {'theme': b['theme'], 'arc': b['arc'], 'cast': sorted(c['name'] for c in b['characters']),
            'conflict': b['conflict'], 'solution_tag': b['solution_tag'], 'ending': story['ending']['title'] if story.get('ending') else None}

class Pipeline:
    def __init__(self, store, provider, fault=None):
        self.store, self.provider, self.fault = store, provider, fault
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))['assets']
        self.character_bible = json.loads(MANIFEST_PATH.with_name('character_bible.json').read_text(encoding='utf-8'))
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None

    def start(self):
        self.store.recover()
        self.thread = threading.Thread(target=self.run, daemon=True, name='storybook-worker')
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)

    def run(self):
        while not self.stop.is_set():
            job = self.store.next_job()
            if not job:
                self.wake.wait(0.5)
                self.wake.clear()
                continue
            self.process(job)

    def process(self, job):
        calls = 0
        last_wire_answer = None
        request = json.loads(job['request'])
        source = self.store.story(job['story']) if job['kind'] == 'turn' else None
        def invoke(stage, context, model):
            nonlocal calls, last_wire_answer
            if calls >= 4:
                raise BudgetExceeded('per-attempt call limit reached')
            total = self.store.usage(job['story'] or job['id'], job['id'] if job['kind'] == 'create' else None)
            if len(total) >= int(os.environ.get('XCMQY_BOOK_CALL_LIMIT', '120')):
                raise BudgetExceeded('book call budget reached; progress preserved')
            if sum(m['input_tokens'] + m['output_tokens'] for m in total) >= int(os.environ.get('XCMQY_BOOK_TOKEN_LIMIT', '300000')):
                raise BudgetExceeded('book token budget reached; progress preserved')
            dollar_limit = float(os.environ.get('XCMQY_BOOK_USD_LIMIT', '0'))
            if dollar_limit and (any(m['cost_usd'] is None for m in total) or sum(m['cost_usd'] or 0 for m in total) >= dollar_limit):
                raise BudgetExceeded('cost budget reached or prices not configured')
            calls += 1
            phase = 'reviewing' if stage == 'review' else 'planning' if stage in {'concepts', 'blueprint'} else 'generating'
            self.store.phase(job['id'], phase)
            if self.fault:
                self.fault(phase)
            # Reserve a durable call before sending: a process crash must not erase usage.
            metric_index=self.store.metric(job['id'], {'stage':stage,'provider':getattr(self.provider,'model','fixture-v2'),
                'mock':self.provider.is_mock,'input_tokens':0,'output_tokens':0,'cost_usd':None,
                'seconds':0,'success':False,'usage_known':False,'interrupted':True})
            context=json.loads(json.dumps(context))
            if 'manifest' in context:
                context['manifest']={a:{k:v for k,v in spec.items() if k not in {'path','width','height','bytes','sha256','alpha'}} for a,spec in context['manifest'].items()}
            model_context={**context,'character_bible':self.character_bible}
            wire_model=model
            intent=getattr(self.provider,'intention_protocol',False)
            if intent and stage in {'setup','setup_repair'}:
                wire_model=model_protocol.ModelOpening
                model_context['role_ids']=model_protocol.roles(context['settings'],context['selected'])
            elif intent and stage in {'proposal','repair'}:
                wire_model=model_protocol.ModelTurn
            if not self.provider.is_mock:
                model_context=compact_context(stage,model_context)
            if intent and wire_model!=model:
                model_context['intention_protocol']=True
                model_context['output_notes']='本次使用简明意图协议，不输出effects/prerequisites/illustration/state_snapshot等底层字段。learn填写线索ID数组，take填写可及物品ID数组，give是物品ID到接收者ID，spend是资源ID到正数。page.characters是人物ID到表情名calm/happy/thinking/surprised/worried/determined，page.items是物品ID列表。反馈、trait、hotspot都在action里；不要放在interaction里。所有生成内容仍须严格符合本次schema。'
                if stage in {'setup','setup_repair'}:
                    model_context['output_notes']+='profiles的键必须使用role_ids给出的ID。tasks用knowledge线索ID数组、owners物品ID到目标主人、relationships伙伴ID到最低值；不要输出conditions。必须同时输出blueprint与page。'
                else:
                    model_context['output_notes']+='本轮只输出ModelTurn，不能输出blueprint。page的新动作不能重复post_action_state已有信息；page.text只描述action_events或events已确认的事实，不能提前叙述下一步按钮的未执行后果。'
            wire_schema=wire_model.model_json_schema()
            age=(context.get('settings') or context.get('story',{}).get('settings') or {}).get('age')
            if wire_model in {model_protocol.ModelOpening,model_protocol.ModelTurn} and age:
                wire_schema['$defs']['ModelPage']['properties']['text'].update(
                    minLength=60 if age=='6-8' else 100,maxLength=120 if age=='6-8' else 180)
                model_context['page_text_target']='正文目标80–100字，上限120字。' if age=='6-8' else '正文目标130–160字，上限180字。'
                defs=wire_schema['$defs']
                ids=list(model_context.get('role_ids') or (context.get('post_action_state') or {}).get('characters',{}))
                defs['ModelPage']['properties']['characters']['propertyNames']={'enum':ids}
                defs['TraitUse']['properties']['character']['enum']=ids
                if wire_model==model_protocol.ModelOpening:
                    defs['ModelBlueprint']['properties']['profiles']['propertyNames']={'enum':ids}
                    defs['ModelTask']['properties']['relationships']['propertyNames']={'enum':[cid for cid in ids if cid!='player']}
                    defs['ModelTask']['properties']['owners']['additionalProperties']['enum']=ids+model_context['asset_catalog']['scenes']
                elif not request.get('text'):
                    facts=context['post_action_state'];props=defs['ModelAction']['properties']
                    props['learn']['items']['enum']=list(context['story']['blueprint']['clues'])
                    for field in ['take','consume','craft','inputs']:
                        if facts['items']:props[field]['items']['enum']=list(facts['items'])
                        else:props[field]['maxItems']=0
                    for field,keys in [('give',facts['items']),('promises',facts['promises']),('spend',facts['resources']),('relationships',facts['relationships'])]:
                        if keys:props[field]['propertyNames']={'enum':list(keys)}
                        else:props[field]['maxProperties']=0
                    if facts['items']:defs['ModelPage']['properties']['items']['items']['enum']=list(facts['items'])
                    else:defs['ModelPage']['properties']['items']['maxItems']=0
                    model_context['output_notes']+='禁止新增未声明的承诺ID。不要把文案差异或trait说明当作状态后果；两种办法的learn/take/give/spend/relationships至少一项真实不同。'
            answer=self.provider.call(stage,model_context,wire_schema,lambda metric:self.store.metric(job['id'],metric,metric_index))
            if stage in {'setup','setup_repair','proposal','repair'}:
                last_wire_answer = answer
            if intent and wire_model!=model:
                try:
                    answer=wire_model.model_validate(answer).model_dump()
                    if stage in {'setup','setup_repair'}:
                        b=model_protocol.blueprint(answer['blueprint'],context['settings'],context['selected'])
                        state=initial_state(StoryBlueprint.model_validate(b).model_dump(),self.manifest)
                        answer={'blueprint':b,'page':model_protocol.page(answer['page'],state,self.manifest)}
                    else:answer=model_protocol.turn(answer,source,request,self.manifest)
                except ValidationError as exc:
                    raise RuleError('; '.join('.'.join(map(str,e['loc']))+': '+e['msg'] for e in exc.errors())[:1200]) from exc
                except ValueError as exc:
                    raise RuleError(str(exc)) from exc
            return model.model_validate(answer).model_dump()
        try:
            if job['kind'] == 'create':
                settings = request['settings']
                manifest = {a: s for a, s in self.manifest.items() if a in settings['assets']}
                recent = [fingerprint(s) for s in self.store.books(job['account']) if s.get('ending')][:10]
                concepts = invoke('concepts', {'settings': settings, 'manifest': manifest, 'recent': recent}, Concepts)['candidates']
                known_names={s.get('character') for s in manifest.values() if s['kind']=='character'}
                candidates=[c for c in concepts if (not settings.get('arc') or c['arc']==settings['arc'])
                            and settings['character'] in c['cast'] and set(c['cast'])<=known_names]
                if not candidates:
                    raise RuleError('requested story structure absent from candidates')
                def score(c):
                    repetition = sum(sum([c['arc'] == r['arc'], sorted(c['cast']) == r['cast'], c['conflict'] == r['conflict'],c['solution_tag'] == r['solution_tag']]) for r in recent)
                    coverage = sum(any(a.get('character') == name for a in manifest.values()) for name in c['cast'])
                    return coverage * 3 - repetition * 4 + (10 if settings.get('arc') == c['arc'] else 0)
                high = max(score(c) for c in candidates)
                selected = secrets.choice([c for c in candidates if score(c) == high])
                setup_context={'settings':settings,'manifest':manifest,'recent':recent,'selected':selected}
                errors=[]
                combined=getattr(self.provider,'combined_setup',False)
                for attempt in range(2 if combined else 1):
                    try:
                        if combined:
                            setup=invoke('setup' if not attempt else 'setup_repair', setup_context if not attempt else {**setup_context,'previous':last_wire_answer,'issues':errors},StoryOpening)
                            b,page=setup['blueprint'],setup['page']
                        else:
                            b=invoke('blueprint',setup_context,StoryBlueprint)
                        if b['arc']!=selected['arc'] or b['theme']!=settings['theme']:
                            raise RuleError('blueprint changed the selected concept or theme')
                        if sorted(selected['cast'])!=sorted(c['name'] for c in b['characters']):
                            raise RuleError('blueprint changed the selected character combination')
                        state=initial_state(b,manifest)
                        if state['characters']['player']['name']!=settings['character']:
                            raise RuleError('blueprint changed the selected player')
                        if not combined:
                            page=invoke('opening',{'settings':settings,'manifest':manifest,'blueprint':b,'state':state},BookPage)
                        validate_page(page,state,b,manifest,[],settings['assets'],settings['age'])
                        break
                    except (RuleError,ModelError,ValueError) as exc:
                        errors=[str(exc)[:1200]]
                        if 'page' in locals() and 'state' in locals() and 'b' in locals():
                            errors+=page_diagnostics(page,state,b,manifest,[],settings)
                        if attempt or not combined or isinstance(exc,BudgetExceeded):raise
                review = invoke('review', {'blueprint': b, 'state': state, 'draft': page, 'settings': settings, 'manifest': manifest}, Review)
                if not review['approved'] or review['issues']:
                    raise RuleError('opening review rejected')
                page['state_snapshot'] = state
                story = {'schema_version': 2, 'id': job['id'], 'settings': settings, 'blueprint': b, 'state': state,
                         'initial_blueprint':json.loads(json.dumps(b)), 'events': [], 'pages': [page], 'manifest': manifest, 'ending': None, 'status': 'active',
                         'mock': self.provider.is_mock, 'concepts': concepts, 'selected_concept': selected, 'usage': []}
            else:
                if source['status'] == 'continued':
                    raise RuleError('page allowance reached; book saved as to be continued')
                if request.get('clarification_job'):
                    clarification = self.store.job(request['clarification_job'], job['account'])
                    result = clarification.get('result') or {}
                    if clarification['story'] != source['id'] or result.get('version') != source['state']['version']:
                        raise RuleError('clarification belongs to another story or version')
                    chosen = next((a for a in result.get('clarification', []) if a['id'] == request['clarification_action']), None)
                    if not chosen:
                        raise RuleError('unknown clarification action')
                    known = {a['id']:a for i in source['pages'][-1]['interactions'] for a in i['actions']}
                    if chosen['id'] in known:
                        if chosen != known[chosen['id']]:
                            raise RuleError('clarification attempts to change an offered action')
                        operation = {'action_id': chosen['id']}
                        if chosen.get('inputs'):
                            operation['items'] = chosen['inputs']
                        for inter in source['pages'][-1]['interactions']:
                            if inter.get('order_action') == chosen['id']:
                                operation['order'] = inter['order']
                        if chosen['verb'] == 'allocate':
                            operation['amount'] = -next(e['value'] for e in chosen['effects'] if e['op'] == 'resource')
                        request['operations'].append(operation)
                        request['text'] = ''
                    else:
                        request['text'] = chosen['label']
                    request['confirmed_understanding'] = chosen
                state, events = apply_operations(source, request['operations'], request.get('reason', ''))
                context = {**for_generation(source,state,events), 'request':request}
                errors = []
                for attempt in range(2):
                    try:
                        proposal = invoke('proposal' if attempt == 0 else 'repair', context if attempt == 0 else {**context, 'previous': last_wire_answer if getattr(self.provider,'intention_protocol',False) else proposal if 'proposal' in locals() else None, 'issues': errors}, TurnProposal)
                        if request.get('confirmed_understanding') and request.get('text') and proposal.get('resolved_action') != request['confirmed_understanding']:
                            raise RuleError('confirmed understanding must be executed exactly')
                        story = accept_proposal(source, request, proposal)
                        review = invoke('review', {**context, 'proposal': proposal, 'confirmed_preview': review_preview(story),
                                                  'check': ['facts', 'causes', 'negation', 'voice', 'repetition', 'illustration']}, Review)
                        if not review['approved'] or review['issues']:
                            raise RuleError('semantic review: ' + '; '.join(review['issues']))
                        break
                    except (RuleError, ModelError, ValueError) as exc:
                        errors = [str(exc)[:500]]
                        if 'proposal' in locals() and not proposal.get('resolved_action') and not proposal.get('events'):
                            errors+=page_diagnostics(proposal.get('page'),state,source['blueprint'],source['manifest'],
                                [e['id'] for e in source['events']+events],source['settings'])
                        if attempt or isinstance(exc, BudgetExceeded):
                            raise
                if story is None:
                    self.store.complete_without_change(job['id'], {'story_id': source['id'], 'version': source['state']['version'], 'clarification': proposal['clarification'], 'clarification_job': job['id']})
                    return
            story['usage'] = self.store.usage(story['id'], job['id'] if job['kind'] == 'create' else None)
            replay(story)
            StoryRecord.model_validate(story)
            self.store.phase(job['id'], 'committing')
            self.store.commit(job, story, fault=self.fault)
            if self.fault:
                self.fault('response')
        except Exception as exc:
            # A response fault after commit must never turn a confirmed result into a retryable failure.
            if self.store.job(job['id'])['phase'] != 'complete':
                message = str(exc)[:400] if isinstance(exc, (RuleError, BudgetExceeded)) else 'generation unavailable; confirmed state preserved'
                self.store.fail(job['id'], message)
