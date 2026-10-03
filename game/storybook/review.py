"""All achievements and family reflections derive from the confirmed ending."""
from copy import deepcopy

def reflection(story):
    ending = story.get('ending')
    if not ending:
        return None
    events = {e['id']:e for e in story['events']}
    return {'book_id':story['id'], 'ending':deepcopy(ending),
            'discoveries':[story['blueprint']['clues'][cid] for cid in ending['discoveries']],
            'helped':[story['state']['characters'][cid]['name'] for cid in ending['helped']],
            'actions':[{'event_id':eid,'description':events[eid]['description'],'reason':events[eid].get('reason','')} for eid in ending['evidence']],
            'badge':{'id':'book.route.'+story['blueprint']['arc'],'title':'完成一本森林绘本','evidence':list(ending['evidence'])}}

def record_completion(account, story):
    report = reflection(story)
    if report is None:
        return False
    reports = account.setdefault('family_reviews_v2', {})
    first = story['id'] not in reports
    reports[story['id']] = report
    account.setdefault('book_badges_v2', {})[story['id']] = report['badge']
    if first:
        stats=account['play_stats']
        stats['total_plays'] += 1
        name=story['settings']['character']
        if name not in stats['characters_used']:
            stats['characters_used'].append(name)
        counts=stats['character_play_counts']
        counts[name] = counts.get(name,0)+1
    return first
