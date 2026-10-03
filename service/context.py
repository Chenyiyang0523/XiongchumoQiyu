"""Keep canonical facts, causal evidence and unfinished tasks; bound prose history."""
from copy import deepcopy
from storybook.engine import can_close
from service.pacing import frontier

def for_generation(story, state, events):
    prior = story['events']
    relevant_ids = set(state['provenance'].values()) | {e['id'] for e in prior[-8:]}
    relevant = [e for e in prior if e['id'] in relevant_ids]
    compact = {k: deepcopy(story[k]) for k in ['id', 'settings', 'blueprint', 'state']}
    compact['manifest'] = {aid: {k:v for k,v in spec.items() if k not in {'path','width','height','bytes','sha256','alpha'}} for aid,spec in story['manifest'].items()}
    compact['pages'] = deepcopy(story['pages'][-1:])
    for page in compact['pages']:
        page.pop('state_snapshot', None)
    compact['page_count'] = len(story['pages'])
    compact['events'] = deepcopy(relevant)
    compact['previous_prose'] = [{'id':p['id'], 'text':p['text'], 'choices':p['choices'], 'discussion':p.get('discussion','')} for p in story['pages'][-3:-1]]
    all_events=prior+events
    kinds=sorted({e['interaction_kind'] for e in all_events if e.get('interaction_kind')})
    callback_pages=sum(bool(p['callbacks']) for p in story['pages'])
    traits=any(e.get('trait_use') for e in all_events)
    closure={'core_tasks_and_promises_complete':can_close(state,story['blueprint']),
             'pages_read':len(story['pages']),'planned_pages':story['settings']['pages'],
             'interaction_types_used':kinds,'callback_pages':callback_pages,'trait_used':traits}
    closure['ending_allowed']=closure['core_tasks_and_promises_complete'] and len(story['pages'])>=story['settings']['pages'] and len(kinds)>=3 and callback_pages>=2 and traits
    closure.update(frontier(state,story['blueprint']))
    closure['pages_remaining']=max(0,story['settings']['pages']+2-len(story['pages']))
    return {'story': compact, 'post_action_state': state, 'action_events': events,'closure_readiness':closure,
            'pace': 'resolve' if len(story['pages']) >= max(4,round(story['settings']['pages']*.6)) else 'explore',
            'relevant_events': relevant, 'unresolved': [q for q in story['blueprint']['quests'] if state['quests'][q['id']] != 'complete']}

def review_preview(story):
    if story is None:
        return None
    return {'state':story['state'], 'page':story['pages'][-1], 'ending':story['ending'], 'events':story['events'][-5:], 'status':story['status']}
