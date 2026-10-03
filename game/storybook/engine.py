"""Canonical state reducer. Models propose; this module decides what can become fact."""
from copy import deepcopy
import re

VERBS = {'observe', 'move', 'ask', 'use', 'combine', 'allocate', 'negotiate', 'reason'}
KINDS = {'observe', 'evidence', 'items', 'dialogue', 'allocation'}
VERB_KINDS = {'observe':'observe','move':'observe','ask':'dialogue','use':'items','combine':'items','allocate':'allocation','negotiate':'dialogue','reason':'evidence'}
ID_PATTERN = re.compile(r'^[a-z][a-z0-9_.-]{0,79}$')

class RuleError(ValueError):
    pass

def require(test, message):
    if not test:
        raise RuleError(message)

def unique(values, label):
    require(len(values) == len(set(values)), 'duplicate ' + label)
    require(all(ID_PATTERN.fullmatch(v) for v in values), 'invalid ' + label)

def validate_recipes(items):
    visited=set()
    def visit(iid, stack):
        require(iid in items and iid not in stack, 'cyclic or unknown recipe ingredient')
        if iid in visited:
            return
        for ingredient in items[iid].get('recipe', []):
            visit(ingredient, stack | {iid})
        visited.add(iid)
    for iid in items:
        visit(iid, set())

def initial_state(blueprint, manifest):
    unique([c['id'] for c in blueprint['characters']], 'character IDs')
    unique([i['id'] for i in blueprint['items']], 'item IDs')
    unique([q['id'] for q in blueprint['quests']], 'quest IDs')
    unique(list(blueprint['clues']), 'clue IDs')
    unique(list(blueprint['resources']), 'resource IDs')
    unique(list(blueprint.get('promises', {})), 'promise IDs')
    require(any(q['required'] for q in blueprint['quests']), 'no core quest')
    require(any(c['id'] == 'player' for c in blueprint['characters']), 'player absent')
    chars = {c['id']: deepcopy(c) for c in blueprint['characters']}
    require(len({c['name'] for c in chars.values()}) == len(chars), 'duplicate character identity')
    require(len({c['location'] for c in chars.values()}) >= 1, 'locations absent')
    for c in chars.values():
        require(c['name'] in {a.get('character') for a in manifest.values() if a['kind'] == 'character'}, 'character outside this world')
        require(all(c.get(k, '').strip() for k in ('motivation','strength','weakness')), 'character motivation or traits absent')
        require(c['location'] in manifest and manifest[c['location']]['kind'] == 'scene', 'invalid location')
        require(set(c['knowledge']) <= set(blueprint['clues']), 'unknown initial knowledge')
    state = {'schema_version': 2, 'version': 1, 'location': chars['player']['location'],
             'characters': chars, 'items': {i['id']: deepcopy(i) for i in blueprint['items']},
             'resources': deepcopy(blueprint['resources']), 'relationships': {c: 0 for c in chars if c != 'player'},
             'knowledge': list(chars['player']['knowledge']), 'quests': {q['id']: 'open' for q in blueprint['quests']},
             'promises': deepcopy(blueprint.get('promises', {})), 'rewards': [], 'provenance': {}}
    for item in state['items'].values():
        require(item['owner'] in chars or item['owner'] in manifest and manifest[item['owner']]['kind']=='scene' or (item['owner'] == 'unmade' and len(item.get('recipe',[])) >= 2), 'unknown owner')
        require(item['asset'] in manifest and manifest[item['asset']]['kind'] == 'prop', 'unknown item asset')
        require(set(item.get('recipe', [])) <= set(state['items']) and item['id'] not in item.get('recipe', []), 'invalid recipe')
        require(len(item.get('recipe', [])) == len(set(item.get('recipe', []))), 'duplicate recipe ingredient')
    validate_recipes(state['items'])
    require(all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in state['resources'].values()), 'invalid resource')
    # Reject cyclic dependencies and impossible/unknown facts before accepting a blueprint.
    quests = {q['id']: q for q in blueprint['quests']}
    def visit(qid, stack):
        require(qid in quests, 'unknown quest dependency')
        require(qid not in stack, 'cyclic quest dependency')
        for dep in quests[qid]['dependencies']:
            visit(dep, stack | {qid})
    for quest in quests.values():
        visit(quest['id'], set())
        for condition in quest['conditions']:
            condition_value(state, condition, blueprint)
    state['provenance'] = {key: 'initial' for key in fact_keys(state)}
    refresh_quests(state, blueprint, 'initial')
    return state

def fact_keys(s):
    return ([f'item:{k}' for k in s['items']] + [f'character:{k}' for k in s['characters']] +
            [f'resource:{k}' for k in s['resources']] + [f'quest:{k}' for k in s['quests']] +
            [f'knowledge:{k}' for k in s['knowledge']] + [f'promise:{k}' for k in s['promises']] +
            [f'relationship:{k}' for k in s['relationships']])

def condition_value(s, c, b):
    kind, key = c['kind'], c['key']
    if kind == 'knowledge':
        require(key in b['clues'], 'unknown clue')
        require(c.get('actor', 'player') in s['characters'], 'unknown knower')
        return key in s['characters'][c.get('actor', 'player')]['knowledge']
    table = {'owner': 'items', 'location': 'characters', 'resource': 'resources',
             'relationship': 'relationships', 'quest': 'quests', 'promise': 'promises'}.get(kind)
    require(table is not None and key in s[table], 'unknown condition key')
    v = s[table][key]
    return v['owner'] if kind == 'owner' else v['location'] if kind == 'location' else v

def matches(s, condition, b):
    actual = condition_value(s, condition, b)
    expected = condition['value']
    comparison = condition.get('comparison', 'eq')
    if comparison == 'eq':
        return actual == expected
    require(type(actual) == type(expected) == int, 'non-numeric comparison')
    return actual >= expected if comparison == 'gte' else actual <= expected

def refresh_quests(s, b, cause):
    for _ in range(len(b['quests'])):
        for q in b['quests']:
            if s['quests'][q['id']] != 'complete' and all(s['quests'][d] == 'complete' for d in q['dependencies']) and all(matches(s, c, b) for c in q['conditions']):
                s['quests'][q['id']] = 'complete'
                s['provenance']['quest:' + q['id']] = cause

def effects(s, action, b, manifest, event_id):
    require(action['verb'] in VERBS, 'unknown verb')
    target = action['target']
    require(target in s['characters'] or target in s['items'] or target in b['clues'] or target in s['resources'] or target in manifest or target in s['quests'] or target in s['promises'], 'unknown action target')
    for c in action.get('prerequisites', []):
        require(matches(s, c, b), 'action prerequisites not met')
    if action['verb'] in {'ask', 'negotiate'}:
        require(target in s['characters'] and s['characters'][target]['location'] == s['location'], 'character absent')
    if action['verb'] in {'use', 'combine'}:
        require(target in s['items'] and s['items'][target]['owner'] == 'player', 'item not owned')
    if action['verb'] == 'allocate':
        expenses=[e for e in action['effects'] if e['op']=='resource']
        require(target in s['resources'] and len(expenses)==1 and expenses[0]['target']==target and type(expenses[0]['value']) is int and expenses[0]['value']<0, 'allocation must specify one actual resource expense')
    trait = action.get('trait_use')
    if trait:
        require(trait['character'] in s['characters'] and trait['aspect'] in {'strength','weakness'}, 'unknown trait')
        require(s['characters'][trait['character']]['location'] == s['location'], 'trait character absent')
        require(bool(s['characters'][trait['character']][trait['aspect']]), 'trait absent')
    if action.get('inputs'):
        require(action['verb'] in {'use','combine'} and len(set(action['inputs'])) == len(action['inputs']), 'invalid item input')
        require(all(i in s['items'] and s['items'][i]['owner'] == 'player' for i in action['inputs']), 'input item unavailable')
    for e in action.get('effects', []):
        op, key, value, actor = e['op'], e['target'], e['value'], e.get('actor', 'player')
        require(actor in s['characters'], 'unknown actor')
        if op == 'learn':
            require(key in b['clues'] and value is True, 'invalid knowledge')
            if key not in s['characters'][actor]['knowledge']:
                s['characters'][actor]['knowledge'].append(key)
            if actor == 'player' and key not in s['knowledge']:
                s['knowledge'].append(key)
            fact = 'knowledge:' + key if actor == 'player' else 'character:' + actor
        elif op == 'move':
            require(key in s['characters'] and value in manifest and manifest[value]['kind'] == 'scene', 'invalid movement')
            s['characters'][key]['location'] = value
            if key == 'player':
                s['location'] = value
            fact = 'character:' + key
        elif op == 'craft':
            require(action['verb'] == 'combine' and key in s['items'] and s['items'][key]['owner'] == 'unmade' and value is True, 'invalid crafting')
            ingredients = s['items'][key].get('recipe', [])
            require(len(ingredients) >= 2 and all(s['items'][i]['owner'] == actor for i in ingredients), 'craft ingredients missing')
            require(set(action.get('inputs', []))==set(ingredients) and action['target'] in ingredients,'craft recipe differs from selected inputs')
            for ingredient in ingredients:
                s['items'][ingredient]['owner'] = 'consumed'
                s['provenance']['item:' + ingredient] = event_id
            s['items'][key]['owner'] = actor
            fact = 'item:' + key
        elif op in {'transfer', 'consume'}:
            require(key in s['items'] and s['items'][key]['owner'] not in {'consumed','unmade'}, 'item unavailable')
            owner = s['items'][key]['owner']
            require(owner == actor or owner == s['location'] or (owner in s['characters'] and s['characters'][owner]['location'] == s['location']), 'item inaccessible')
            if op == 'consume':
                require(owner == actor, 'cannot consume unowned item')
                value = 'consumed'
            else:
                require(value in s['characters'] or value == s['location'], 'invalid recipient')
                if value in s['characters']:
                    require(s['characters'][value]['location'] == s['location'], 'recipient absent')
            s['items'][key]['owner'] = value
            fact = 'item:' + key
        elif op in {'resource', 'relationship'}:
            table = 'resources' if op == 'resource' else 'relationships'
            require(key in s[table] and type(value) is int, 'invalid numeric effect')
            require(op != 'resource' or value <= 0, 'resource cannot appear without a transfer')
            require(abs(value) <= 20, 'numeric effect too large')
            new = s[table][key] + value
            require(new >= 0 if op == 'resource' else -10 <= new <= 10, 'insufficient resource or relationship range')
            s[table][key] = new
            fact = ('resource:' if op == 'resource' else 'relationship:') + key
        elif op == 'promise':
            require(key in s['promises'] and type(value) is bool, 'unknown promise')
            s['promises'][key] = value
            fact = 'promise:' + key
        elif op == 'reward':
            require(key in s['quests'] and s['quests'][key] == 'complete', 'reward before completion')
            require(key not in s['rewards'], 'duplicate reward')
            s['rewards'].append(key)
            fact = 'quest:' + key
        else:
            raise RuleError('unsupported effect')
        s['provenance'][fact] = event_id
    refresh_quests(s, b, event_id)

def available_actions(page):
    return {a['id']: a for i in page['interactions'] for a in i['actions']}

def apply_operations(story, operations, reason='', free_action=None):
    b, manifest = story['blueprint'], story['manifest']
    s = deepcopy(story['state'])
    page = story['pages'][-1]
    actions = available_actions(page)
    ids = [op['action_id'] for op in operations]
    require(len(ids) == len(set(ids)), 'duplicate operation')
    events = []
    if free_action is not None:
        require(free_action['id'] not in actions or free_action == actions[free_action['id']], 'free action attempts to overwrite offered action')
        actions[free_action['id']] = free_action
        operation = {'action_id':free_action['id'], 'items':free_action.get('inputs', [])}
        if free_action['verb'] == 'allocate':
            expense = next((e for e in free_action['effects'] if e['op'] == 'resource'), None)
            require(expense is not None, 'free allocation has no resource cost')
            operation['amount'] = -expense['value']
        for inter in page['interactions']:
            if inter.get('order_action') == free_action['id']:
                operation['order'] = inter['order']
        operations = list(operations) + [operation]
    for index, op in enumerate(operations):
        require(op['action_id'] in actions, 'unknown action ID')
        action = deepcopy(actions[op['action_id']])
        if action.get('inputs'):
            require(set(op.get('items', [])) == set(action['inputs']), 'selected ingredients mismatch')
        interaction = next((i for i in page['interactions'] if op['action_id'] in [a['id'] for a in i['actions']]), None)
        if interaction and interaction.get('order_action') == action['id']:
            require(op.get('order') == interaction['order'], 'evidence order incorrect')
        if action['verb'] == 'allocate':
            require(op.get('amount') is not None, 'allocation amount missing')
            resource_effect = next((e for e in action['effects'] if e['op'] == 'resource'), None)
            require(resource_effect is not None and op['amount'] == -resource_effect['value'], 'allocation amount mismatch')
        eid = 'event.%s.%s' % (s['version'] + 1, index)
        before = deepcopy(s)
        effects(s, action, b, manifest, eid)
        require({k:v for k,v in s.items() if k != 'provenance'} != {k:v for k,v in before.items() if k != 'provenance'}, 'action has no state consequence')
        events.append({'schema_version': 2, 'id': eid, 'turn': s['version'] + 1,
                       'cause': ['page:' + page['id']], 'action_id': action['id'],
                       'verb':action['verb'],
                       'description': action['feedback'], 'effects': action['effects'], 'reason': reason,
                       'interaction_kind':VERB_KINDS[action['verb']],
                       'trait_use':action.get('trait_use')})
    return s, events

def validate_page(page, s, b, manifest, event_ids, assets, age, confirmed_events=None):
    require(page is not None, 'page missing')
    unique([i['id'] for i in page['interactions']], 'interaction IDs')
    unique(list(available_actions(page)), 'action IDs')
    # Compare against the original list as dict construction would hide duplicate IDs.
    raw_ids = [a['id'] for i in page['interactions'] for a in i['actions']]
    unique(raw_ids, 'action IDs')
    illustration = page['illustration']
    require(illustration['scene'] == s['location'], 'scene conflicts with player location')
    used = [illustration['scene']] + list(illustration['characters'].values()) + illustration['props']
    for cid, sprite in illustration['characters'].items():
        require(cid in s['characters'] and s['characters'][cid]['location'] == s['location'], 'pictured character absent')
        require(sprite in manifest and manifest[sprite].get('character') == s['characters'][cid]['name'], 'wrong character sprite')
    for prop in illustration['props']:
        require(any(i['asset'] == prop and (i['owner'] in {s['location'], 'player'} or i['owner'] in s['characters'] and s['characters'][i['owner']]['location'] == s['location']) for i in s['items'].values()), 'pictured item inaccessible')
    key_art = illustration.get('key_art')
    if key_art:
        require(key_art in manifest, 'unknown key art')
        spec = manifest[key_art]
        require(spec['kind'] == 'key_art', 'wrong key art type')
        require(not spec.get('scenes') or s['location'] in spec['scenes'], 'key art location conflict')
        require(set(spec.get('props', [])) == set(illustration['props']), 'key art prop conflict')
        require(not spec.get('event_verbs') or any(e.get('turn') == s['version'] and e.get('verb') in spec['event_verbs'] for e in (confirmed_events or [])), 'key art activity not confirmed')
        require(set(spec.get('characters', [])) == {s['characters'][c]['name'] for c in illustration['characters']}, 'key art cast conflict')
        require(all(matches(s, c, b) for c in spec.get('conditions', [])), 'key art event conflict')
        used.append(key_art)
    require(all(a in manifest and a in assets for a in used), 'asset unavailable to client')
    require(set(page['callbacks']) <= set(event_ids), 'callback refers to unknown event')
    limit = (60, 120) if age == '6-8' else (100, 180)
    require(limit[0] <= len(page['text']) <= limit[1], 'page text outside age band')
    for interaction in page['interactions']:
        require(interaction['kind'] in KINDS, 'unsupported interaction')
        require(len(set(interaction.get('order', []))) == len(interaction.get('order', [])), 'duplicate evidence card')
        if interaction.get('order'):
            require(set(interaction['order']) <= set(b['clues']), 'unknown evidence card')
            require(all(k in s['knowledge'] for k in interaction['order']), 'evidence not yet discovered')
            require(interaction.get('order_action') in [a['id'] for a in interaction['actions']], 'unknown order action')
        outcomes = []
        for action in interaction['actions']:
            if action.get('hotspot'):
                require(action['hotspot'] in used, 'hotspot object absent from illustration')
            trial = deepcopy(s)
            effects(trial, action, b, manifest, 'validation')
            require({k:v for k,v in trial.items() if k != 'provenance'} != {k:v for k,v in s.items() if k != 'provenance'}, 'interaction has no state consequence')
            outcome = {k:v for k,v in trial.items() if k != 'provenance'}
            require(outcome not in outcomes, 'alternative actions have identical consequences')
            outcomes.append(outcome)

def can_close(s, b):
    return all(s['quests'][q['id']] == 'complete' for q in b['quests'] if q['required']) and all(s['promises'].values())

def expand_world(s, b, additions, manifest, cause):
    """Append discoveries; never overwrite established entities or invent owned rewards."""
    items=additions.get('items',[]);clues=additions.get('clues',{});quests=additions.get('quests',[])
    unique([i['id'] for i in items], 'new item IDs');unique(list(clues),'new clue IDs');unique([q['id'] for q in quests],'new quest IDs')
    require(not set(clues)&set(b['clues']), 'cannot overwrite a clue')
    require(not {i['id'] for i in items}&set(s['items']), 'cannot overwrite an item')
    require(not {q['id'] for q in quests}&set(s['quests']), 'cannot overwrite a quest')
    require(len(s['items'])+len(items)<=64 and len(b['clues'])+len(clues)<=80 and len(s['quests'])+len(quests)<=24, 'expansion limit reached')
    available=set(s['items'])|{i['id'] for i in items}
    for item in items:
        require(item['asset'] in manifest and manifest[item['asset']]['kind']=='prop','new item asset unavailable')
        require(item['owner'] == s['location'] or item['owner']=='unmade' and len(item.get('recipe',[]))>=2, 'discovery cannot grant an owned item')
        recipe=item.get('recipe',[])
        require(len(recipe)==len(set(recipe)) and set(recipe)<=available and item['id'] not in recipe,'invalid new recipe')
        s['items'][item['id']]=deepcopy(item);s['provenance']['item:'+item['id']]=cause
    b['items'].extend(deepcopy(items));b['clues'].update(deepcopy(clues))
    validate_recipes(s['items'])
    for q in quests:
        require(q['required'] is False,'new side quest cannot unexpectedly block main closure')
        require(set(q['dependencies'])<=set(s['quests']),'new quest dependencies absent')
        s['quests'][q['id']]='open';s['provenance']['quest:'+q['id']]=cause
        for c in q['conditions']:condition_value(s,c,b)
        b['quests'].append(deepcopy(q))
    refresh_quests(s,b,cause)

def accept_proposal(story, request, proposal):
    require(story.get('ending') is None, 'story already ended')
    require(request['version'] == story['state']['version'], 'stale state version')
    if proposal['clarification']:
        require(not proposal['events'] and proposal['ending'] is None and proposal['page'] is None and proposal['resolved_action'] is None and not proposal.get('expansion'), 'clarification must not alter facts')
        require(bool(request.get('text')), 'clarification requires free player input')
        unique([a['id'] for a in proposal['clarification']], 'clarification action IDs')
        for candidate in proposal['clarification']:
            # Validate the entire meaning, not just an ID that could disguise another action.
            apply_operations(story, request.get('operations', []), request.get('reason', ''), candidate)
        return None
    require(bool(request.get('text')) == bool(proposal.get('resolved_action')), 'free text must be interpreted explicitly')
    working=deepcopy(story)
    introduced=[]
    if proposal.get('expansion'):
        require(proposal.get('resolved_action') is not None, 'new discoveries must follow an explicit player intention')
        eid='event.%s.intro'%(story['state']['version']+1)
        expand_world(working['state'],working['blueprint'],proposal['expansion'],working['manifest'],eid)
        introduced=[{'schema_version':2,'id':eid,'turn':story['state']['version']+1,'cause':['page:'+story['pages'][-1]['id']],
                     'action_id':proposal['resolved_action']['id'],'verb':proposal['resolved_action']['verb'],
                     'description':'通过这次行动确认的新发现。','effects':[],'reason':request.get('reason',''),'expansion':deepcopy(proposal['expansion'])}]
    state, events = apply_operations(working, request['operations'], request.get('reason', ''), proposal.get('resolved_action'))
    events = introduced + events
    require(events, 'no action submitted')
    seen = {e['id'] for e in story['events'] + events}
    # Narrative events can move or inform established NPCs, with explicit prior causes.
    for event in proposal['events']:
        require(not event.get('expansion'), 'narrative events cannot inject discoveries')
        require(event['id'] not in seen and event['cause'] and set(event['cause']) <= seen, 'event lacks causal provenance')
        require(event['turn'] == state['version'] + 1, 'wrong event turn')
        require(all(e['op'] in {'learn', 'move'} and (e['target'] != 'player' if e['op'] == 'move' else e.get('actor', 'player') != 'player') for e in event['effects']), 'model cannot silently change player facts')
        proxy = {'verb': 'observe', 'target': next(iter(state['characters'])), 'effects': event['effects']}
        effects(state, proxy, working['blueprint'], working['manifest'], event['id'])
        events.append(event)
        seen.add(event['id'])
    result = deepcopy(working)
    result['pages'][-1]['choices'] = request['operations'] + ([{'action_id': proposal['resolved_action']['id'], 'text': request['text'], 'label':proposal['resolved_action']['label']}] if request.get('text') else [])
    result['pages'][-1]['discussion'] = request.get('reason', '')
    result['events'].extend(events)
    state['version'] += 1
    result['state'] = state
    kinds = {e.get('interaction_kind') for e in result['events'] if e.get('interaction_kind')}
    if proposal['ending']:
        require(can_close(state, result['blueprint']), 'necessary quest or promise unresolved')
        require(len(story['pages']) >= story['settings']['pages'], 'premature ending')
        require(len(kinds) >= 3, 'fewer than three consequential interaction types')
        require(sum(bool(p['callbacks']) for p in story['pages']) >= 2, 'insufficient callbacks')
        require(any(e.get('trait_use') for e in result['events']), 'character traits never affected an action')
        ending = proposal['ending']
        require(set(ending['evidence']) <= seen and ending['evidence'], 'ending evidence absent')
        require(set(ending['discoveries']) <= set(state['knowledge']), 'invented ending discovery')
        require(set(ending['helped']) <= set(state['characters']), 'invented helped character')
        require(proposal['page'] is None, 'ending must be a single confirmed record')
        result['ending'] = ending
        result['status'] = 'complete'
    else:
        validate_page(proposal['page'], state, result['blueprint'], story['manifest'], seen,
                      story['settings']['assets'], story['settings']['age'], result['events'])
        require(proposal['page']['id'] not in {p['id'] for p in story['pages']}, 'duplicate page')
        accepted_page = deepcopy(proposal['page'])
        accepted_page['state_snapshot'] = deepcopy(state)
        result['pages'].append(accepted_page)
        result['status'] = 'continued' if len(result['pages']) >= story['settings']['pages'] + 2 else 'active'
    return result

def replay(story):
    blueprint = deepcopy(story.get('initial_blueprint',story['blueprint']))
    state = initial_state(blueprint, story['manifest'])
    for event in story['events']:
        if event.get('expansion'):
            expand_world(state,blueprint,event['expansion'],story['manifest'],event['id'])
        craft = next((e for e in event['effects'] if e['op'] == 'craft'), None)
        proxy = {'verb': 'combine' if craft else 'observe', 'target': state['items'][craft['target']]['recipe'][0] if craft else 'player', 'inputs':state['items'][craft['target']]['recipe'] if craft else [], 'effects': event['effects']}
        effects(state, proxy, blueprint, story['manifest'], event['id'])
        state['version'] = event['turn']
    require(blueprint == story['blueprint'], 'blueprint expansion/ledger mismatch')
    require(state == story['state'], 'ledger/snapshot mismatch')
    return state
