"""Expose unfinished facts and verify a route towards them, without writing a plot.

The model chooses the event, voice and solution. These checks only prevent late
pages from offering nothing but unrelated facts while a promised goal is stuck.
"""
from copy import deepcopy
from storybook.engine import matches, effects, page_action_contexts, VERB_KINDS, RuleError


def frontier(state, blueprint):
    quests={q['id']:q for q in blueprint['quests']}
    needed={q['id'] for q in quests.values() if q['required'] and state['quests'][q['id']]!='complete'}
    pending=list(needed)
    while pending:
        for dep in quests[pending.pop()]['dependencies']:
            if state['quests'][dep]!='complete' and dep not in needed:
                needed.add(dep);pending.append(dep)
    conditions=[]
    for qid in sorted(needed):
        quest=quests[qid]
        for condition in quest['conditions']:
            if not matches(state,condition,blueprint):
                conditions.append({'quest':qid,'title':quest['title'],**deepcopy(condition)})
    promises=[{'id':key,'description':blueprint.get('promise_descriptions',{}).get(key,key)}
              for key,done in state['promises'].items() if not done]
    return {'unmet_conditions':conditions,'unfulfilled_promises':promises}


def condition_distance(state, condition, blueprint):
    """Bounded physical prerequisites: ownership, ingredients and presence."""
    if matches(state,condition,blueprint):return 0
    kind,key=condition['kind'],condition['key']
    if kind=='relationship':
        comparison=condition.get('comparison','eq');actual=state['relationships'][key]
        gap=max(0,condition['value']-actual) if comparison=='gte' else max(0,actual-condition['value']) if comparison=='lte' else abs(actual-condition['value'])
        return 1+gap+(state['characters'][key]['location']!=state['location'])
    if kind=='owner':
        item=state['items'][key];owner=item['owner']
        if owner=='unmade':
            ingredients=[state['items'][i] for i in item['recipe']]
            missing=[i for i in ingredients if i['owner']!='player']
            locations=[state['characters'][i['owner']]['location'] if i['owner'] in state['characters'] else i['owner'] for i in missing]
            return 2+len(missing)+int(bool(locations) and state['location'] not in locations)
        if owner=='player' and condition['value'] in state['characters']:
            return 1+(state['characters'][condition['value']]['location']!=state['location'])
        location=state['characters'][owner]['location'] if owner in state['characters'] else owner
        return 1+(location!=state['location'])
    return 1


def progress(before, after, blueprint):
    demand=frontier(before,blueprint)
    score=sum(condition_distance(before,c,blueprint)-condition_distance(after,c,blueprint)
              for c in demand['unmet_conditions'])
    score+=sum(after['promises'][p['id']] for p in demand['unfulfilled_promises'])
    return score


def validate_resolution_page(story, context):
    if story.get('ending') or story['status']=='continued':return
    if context['closure_readiness']['ending_allowed']:
        raise RuleError('all closure gates are met: return the evidenced ending, not another page')
    # Earlier resolution may legitimately prepare a discussion or spend time
    # testing an idea. The final three planned pages must offer direct progress.
    if context.get('pace')!='resolve' or len(story['pages'])<story['settings']['pages']-1:return
    state=story['state'];blueprint=story['blueprint'];page=story['pages'][-1]
    demand=frontier(state,blueprint)
    used=set(context['closure_readiness']['interaction_types_used'])
    incomplete=bool(demand['unmet_conditions'] or demand['unfulfilled_promises'])
    if not incomplete and len(used)>=3:return
    contexts=page_action_contexts(page,state,blueprint,story['manifest'])
    for interaction in page['interactions']:
        for action in interaction['actions']:
            for enabling in contexts[action['id']]:
                trial=deepcopy(enabling);effects(trial,action,blueprint,story['manifest'],'pacing-preview')
                if incomplete and progress(state,trial,blueprint)>0:return
                if len(used)<3 and VERB_KINDS[action['verb']] not in used:return
    raise RuleError('resolution page has no executable route advancing unfinished conditions/promises'
                    if incomplete else 'resolution page needs an actually missing interaction verb')
