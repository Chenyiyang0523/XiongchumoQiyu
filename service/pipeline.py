import json
import os
import secrets
import threading
from pathlib import Path
from service.models import Concepts, StoryBlueprint, BookPage, TurnProposal, Review, StoryRecord
from service.provider import BudgetExceeded, ModelError
from service.context import for_generation, review_preview
from storybook.engine import initial_state, validate_page, apply_operations, accept_proposal, replay, RuleError

MANIFEST_PATH = Path(__file__).resolve().parents[1] / 'game/storybook/asset_manifest.json'

def fingerprint(story):
    b = story['blueprint']
    return {'theme': b['theme'], 'arc': b['arc'], 'cast': sorted(c['name'] for c in b['characters']),
            'conflict': b['conflict'], 'solution_tag': b['solution_tag'], 'ending': story['ending']['title'] if story.get('ending') else None}

class Pipeline:
    def __init__(self, store, provider, fault=None):
        self.store, self.provider, self.fault = store, provider, fault
        self.manifest = json.loads(MANIFEST_PATH.read_text())['assets']
        self.character_bible = json.loads(MANIFEST_PATH.with_name('character_bible.json').read_text())
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
        request = json.loads(job['request'])
        source = self.store.story(job['story']) if job['kind'] == 'turn' else None
        def invoke(stage, context, model):
            nonlocal calls
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
            return model.model_validate(self.provider.call(stage, {**context,'character_bible':self.character_bible}, model.model_json_schema(), lambda metric: self.store.metric(job['id'], metric,metric_index))).model_dump()
        try:
            if job['kind'] == 'create':
                settings = request['settings']
                manifest = {a: s for a, s in self.manifest.items() if a in settings['assets']}
                recent = [fingerprint(s) for s in self.store.books(job['account']) if s.get('ending')][:10]
                concepts = invoke('concepts', {'settings': settings, 'manifest': manifest, 'recent': recent}, Concepts)['candidates']
                candidates=[c for c in concepts if not settings.get('arc') or c['arc']==settings['arc']]
                if not candidates:
                    raise RuleError('requested story structure absent from candidates')
                def score(c):
                    repetition = sum(sum([c['arc'] == r['arc'], sorted(c['cast']) == r['cast'], c['conflict'] == r['conflict'],c['solution_tag'] == r['solution_tag']]) for r in recent)
                    coverage = sum(any(a.get('character') == name for a in manifest.values()) for name in c['cast'])
                    return coverage * 3 - repetition * 4 + (10 if settings.get('arc') == c['arc'] else 0)
                high = max(score(c) for c in candidates)
                selected = secrets.choice([c for c in candidates if score(c) == high])
                b = invoke('blueprint', {'settings': settings, 'manifest': manifest, 'recent': recent, 'selected': selected}, StoryBlueprint)
                if b['arc'] != selected['arc'] or b['theme'] != settings['theme']:
                    raise RuleError('blueprint changed the selected concept or theme')
                if sorted(selected['cast']) != sorted(c['name'] for c in b['characters']):
                    raise RuleError('blueprint changed the selected character combination')
                state = initial_state(b, manifest)
                if state['characters']['player']['name'] != settings['character']:
                    raise RuleError('blueprint changed the selected player')
                page = invoke('opening', {'settings': settings, 'manifest': manifest, 'blueprint': b, 'state': state}, BookPage)
                validate_page(page, state, b, manifest, [], settings['assets'], settings['age'])
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
                        proposal = invoke('proposal' if attempt == 0 else 'repair', context if attempt == 0 else {**context, 'previous': proposal if 'proposal' in locals() else None, 'issues': errors}, TurnProposal)
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
