"""Keep canonical facts, causal evidence and unfinished tasks; bound prose history."""
from copy import deepcopy

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
    return {'story': compact, 'post_action_state': state, 'action_events': events,
            'pace': 'resolve' if len(story['pages']) >= story['settings']['pages']-2 else 'explore',
            'relevant_events': relevant, 'unresolved': [q for q in story['blueprint']['quests'] if state['quests'][q['id']] != 'complete']}

def review_preview(story):
    if story is None:
        return None
    return {'state':story['state'], 'page':story['pages'][-1], 'ending':story['ending'], 'events':story['events'][-5:], 'status':story['status']}
