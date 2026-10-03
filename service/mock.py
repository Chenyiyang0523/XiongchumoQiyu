"""Explicit integration fixture, never a fallback for failed real generation."""
from copy import deepcopy
from service.models import StoryBlueprint, BookPage, TurnProposal

def condition(kind, key, value, **kw):
    return {'kind': kind, 'key': key, 'value': value, **kw}

def effect(op, target, value, **kw):
    return {'op': op, 'target': target, 'value': value, **kw}

def action(aid, verb, label, target, changes, feedback, **kw):
    return {'id': aid, 'verb': verb, 'label': label, 'target': target, 'effects': changes, 'feedback': feedback, **kw}

def blueprint(settings, arc='mystery'):
    name = settings['character']
    buddy = '熊大' if name != '熊大' else '赵琳'
    clues = {'clue.trail': '泥土上的痕迹先通往小桥。', 'clue.sound': '远处的铃声晚于足迹出现。',
             'clue.plan': '地图和伙伴的观察指向同一条安全路线。', 'clue.solution': '路线标记已经核对，伙伴能够安全返回。',
             'clue.alternative': '大家约定先沿河观察，再回到集合点。'}
    return StoryBlueprint.model_validate({'title': settings['theme'] + '：林间的约定', 'theme': settings['theme'],
        'arc': arc, 'goal': '弄清铃声的来源，为伙伴标出一条安全回家的路线。', 'conflict': '旧地图有两条岔路，大家对方向有不同判断。',
        'characters': [{'id': 'player', 'name': name, 'location': 'scene.forest', 'motivation': '让伙伴平安回来', 'strength': '仔细观察', 'weakness': '容易着急'},
                       {'id': 'buddy', 'name': buddy, 'location': 'scene.forest', 'motivation': '确认大家的办法', 'strength': '比较线索', 'weakness': '不轻易相信猜想'}],
        'items': [{'id': 'item.map', 'name': '森林地图', 'owner': 'scene.forest', 'asset': 'prop.map'},
                  {'id':'item.footprint','name':'足迹泥块','owner':'scene.forest','asset':'prop.footprint'}],
        'clues': clues, 'quests': [{'id': 'quest.route', 'title': '核对安全路线', 'conditions': [condition('knowledge', 'clue.solution', True)]}],
        'resources': {'time': settings['pages'] * 2, 'materials': 6},
        'promises': {'promise.return': False}, 'twists': ['铃声来自大家约好的集合信号。'], 'closure': '核对路线并履行返回的约定', 'solution_tag': 'compare_and_cooperate'
    }).model_dump()

def page(number, b, state, settings, manifest, events):
    planned = settings['pages']
    ratio = number / planned
    if number == 1:
        kind = 'observe'
        actions = [action('action.%s.trail' % number, 'observe', '查看地面的足迹', 'clue.trail', [effect('learn', 'clue.trail', True)], '你发现足迹先朝小桥延伸。'),
                   action('action.%s.sound' % number, 'observe', '辨认树林里的铃声', 'clue.sound', [effect('learn', 'clue.sound', True)], '你听出铃声来自集合点附近。')]
        text = '一阵铃声穿过树林。旧地图在石头旁展开，两个方向都画着小桥。伙伴把脚步放轻：“猜错了会让大家绕远路。”你蹲下看看泥土，又抬头听了听。风把地图的一角掀起来，仿佛在等你作出第一个判断。'
    elif number == 2:
        kind = 'observe'
        missing = next(k for k in ['clue.trail', 'clue.sound'] if k not in state['knowledge'])
        actions = [action('action.%s.check' % number, 'observe', '再检查另一条线索', missing, [effect('learn', missing, True)], '你补上另一条线索，两个发现终于可以比较。'),
                   action('action.%s.ask' % number, 'ask', '请伙伴一起确认', 'buddy', [effect('learn', missing, True), effect('relationship', 'buddy', 1)], '伙伴用自己的观察帮你补上了线索。')]
        text = '你把刚才的发现讲给伙伴听。对方没有急着指出方向，而是留出一个小小的疑问：“只有这一条，还不能说明全部事情。”地图上的小桥和你发现的痕迹似乎互相呼应。你可以补上另一条线索，也可以邀请伙伴一起核对。'
    elif number == 3:
        kind = 'evidence'
        actions = [action('action.%s.order' % number, 'reason', '按先后顺序摆好线索', 'clue.plan', [effect('learn', 'clue.plan', True)], '足迹先出现，铃声随后响起，你整理出路线的先后。'),
                   action('action.%s.compare' % number, 'ask', '和伙伴比较两种解释', 'buddy', [effect('learn', 'clue.plan', True), effect('relationship', 'buddy', 1)], '伙伴认可你的比较方法，也愿意同行。')]
        text = '足迹和铃声都找到了，可它们到底谁先谁后呢？伙伴用树枝在地上画了两个小框，请你把发现摆进去。先后顺序不同，路线的解释也会不同。你想起前面的观察，准备把两条线索连接起来，或者先与伙伴交换各自的解释。'
    elif number == 4:
        kind = 'items'
        actions = [action('action.%s.collect' % number, 'observe', '收好地图，带着它核对', 'item.map', [effect('transfer', 'item.map', 'player')], '你把地图收进背包，之后可以亲自使用。'),
                   action('action.%s.share' % number, 'negotiate', '请伙伴保管地图', 'buddy', [effect('transfer', 'item.map', 'buddy'), effect('relationship', 'buddy', 1)], '伙伴保管地图，你们分工核对路线。')]
        text = '地图上的折痕刚好压住了小桥。你终于知道，先前让大家困惑的两条线其实是一条路的两段。地图还放在地上，接下来需要有人保管它。你可以自己收进背包，也可以与伙伴商量分工。每一种安排，都会让下一步的合作有所不同。'
    elif number == 5:
        kind = 'items'
        owner = state['items']['item.map']['owner']
        verb, target = ('use', 'item.map') if owner == 'player' else ('ask', 'buddy')
        actions = [action('action.%s.map' % number, verb, '用地图核对路线', target, [effect('learn', 'clue.solution', True)], '保管的地图派上用场，安全路线核对完成。'),
                   action('action.%s.river' % number, 'observe', '沿河观察，再确认标记', 'clue.solution', [effect('resource', 'time', -2), effect('learn', 'clue.solution', True), effect('learn', 'clue.alternative', True)], '你花了两份时间观察河岸，也核对出了安全路线。')]
        text = '刚才的分工现在派上了用场。你们停在路边，对照地图上弯弯的河流。伙伴提醒你，核对路线可以借助现有地图，也可以花些时间观察河岸。两种办法都能得到答案，但所花时间不同。你要怎样把猜想变成可靠的结论呢？'
    elif ratio < .8:
        kind = 'allocation'
        actions = [action('action.%s.quick' % number, 'allocate', '分配1份时间做醒目标记', 'time', [effect('resource', 'time', -1), effect('relationship', 'buddy', 1)], '你们用一份时间作了标记，伙伴感谢你的安排。'),
                   action('action.%s.careful' % number, 'allocate', '分配2份时间一起检查', 'time', [effect('resource', 'time', -2), effect('relationship', 'buddy', 2)], '你们多花一份时间复查，彼此更放心了。')]
        actions = [a for a in actions if -a['effects'][0]['value'] <= state['resources']['time'] and state['relationships']['buddy'] + a['effects'][1]['value'] <= 10]
        if not actions:
            actions = [action('action.%s.share' % number, 'negotiate', '说明剩余资源，约好返回', 'buddy', [effect('promise', 'promise.return', True)], '你坦诚说明情况，并履行返回约定。')]
            kind = 'dialogue'
        text = '路线已经确认，大家终于松了一口气。伙伴看着你留下的标记，想把它做得更清楚。剩下的时间有限，你可以迅速完成，也可以再多花一点时间一起复查。你们认真讨论每一份时间的用处，选择会影响之后能够做些什么。'
    else:
        kind = 'dialogue'
        value = min(1, 10 - state['relationships']['buddy'])
        changes = [effect('promise', 'promise.return', True)] if not state['promises']['promise.return'] else [effect('resource', 'time', -1)]
        if value:
            changes += [effect('relationship', 'buddy', value)]
        actions = [action('action.%s.promise' % number, 'negotiate', '确认返回的约定，感谢伙伴', 'buddy', changes, '你说明自己的办法，大家按约定一起返回。')]
        text = '那阵铃声再次响起，这回你知道它是集合的信号。伙伴指了指已经核对好的路线，笑着问：“你最想告诉大家的是哪个发现？”你想起之前的观察和分工，也记得约定过一起返回。现在，把理由说清楚，让这次合作有一个踏实的收尾吧。'
    interaction = {'id': 'interaction.%s' % number, 'kind': kind, 'instruction': {'observe': '看一看，再选择你的发现', 'evidence': '点击线索按先后顺序排列；也可以换个办法', 'items': '选择如何保管或使用真实物品', 'allocation': '选择分配多少时间', 'dialogue': '和伙伴说清你的办法'}[kind], 'actions': actions}
    if number == 1:
        for a in actions:
            a['hotspot'] = 'prop.footprint' if a['target'] == 'clue.trail' else 'scene.forest'
            a['trait_use'] = {'character':'player','aspect':'strength','explanation':'利用仔细观察的特长获得路线线索。'}
    if number == 3:
        interaction.update(order=['clue.trail', 'clue.sound'], order_action=actions[0]['id'])
    if settings['age'] == '6-8':
        text = text[:115]
    else:
        text += '你也可以写下自己的想法，或和家人讨论这样做的原因。'
        text = text[:178]
    sprites = {c['id']: next(a for a, spec in manifest.items() if spec['kind'] == 'character' and spec['character'] == c['name']) for c in b['characters']}
    props = ['prop.map'] if state['items']['item.map']['owner'] in {'player', state['location']} else []
    if number <= 3: props.append('prop.footprint')
    return BookPage.model_validate({'id': 'page.%s' % number, 'title': ['第一阵铃声', '补上一条线索', '先后之间', '地图的去处', '可靠的结论'][number-1] if number <= 5 else '把约定变成行动',
        'text': text, 'illustration': {'scene': state['location'], 'characters': sprites, 'props': props}, 'interactions': [interaction],
        'callbacks': [events[-1]['id']] if events and number >= 3 else []}).model_dump()

class MockProvider:
    is_mock = True
    def call(self, stage, context, schema, record):
        record({'stage': stage, 'provider': 'fixture-v2', 'mock': True, 'input_tokens': 0, 'output_tokens': 0, 'cost_usd': 0, 'seconds': 0, 'success': True})
        if stage == 'review':
            return {'approved': True, 'issues': []}
        if stage == 'concepts':
            requested = context['settings'].get('arc') or 'mystery'
            arcs = [requested] + [a for a in ['mystery', 'comedy', 'journey'] if a != requested][:2]
            return {'candidates': [{'arc': a, 'title': context['settings']['theme'], 'conflict': '不同的路线判断', 'solution_tag': a, 'cast': [context['settings']['character'], '熊大' if context['settings']['character'] != '熊大' else '赵琳']} for a in arcs]}
        if stage == 'blueprint':
            return blueprint(context['settings'], context['selected']['arc'])
        if stage == 'opening':
            return page(1, context['blueprint'], context['state'], context['settings'], context['manifest'], [])
        if stage in {'proposal', 'repair'}:
            story = context['story']
            request = context['request']
            result = {'page': None, 'events': [], 'resolved_action': None, 'clarification': [], 'ending': None}
            if request.get('text'):
                # Fixture intentionally asks for clarification: never pretends a keyword parser is an LLM.
                result['clarification'] = deepcopy(story['pages'][-1]['interactions'][0]['actions'][:2])
                return TurnProposal.model_validate(result).model_dump()
            state = context['post_action_state']
            events = story['events'] + context['action_events']
            count = story.get('page_count', len(story['pages']))
            if count >= story['settings']['pages']:
                result['ending'] = {'title': '铃声里的约定', 'text': '你核对了安全路线，也履行了与伙伴一起返回的约定。每一步发现和分工，都留在了这本绘本里。',
                    'evidence': [e['id'] for e in events[-3:]], 'discoveries': state['knowledge'], 'helped': ['buddy'], 'solution': '比较线索，与伙伴分工核对路线。'}
            else:
                result['page'] = page(count + 1, story['blueprint'], state, story['settings'], story['manifest'], events)
            return TurnProposal.model_validate(result).model_dump()
        raise ValueError('unsupported fixture stage')
