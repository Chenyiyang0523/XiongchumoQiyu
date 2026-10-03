"""Compact asset capabilities and explicit, stage-specific contracts for live models."""
from copy import deepcopy


GUIDE = '''所有schema必填字段都必须出现，不添加schema外字段。所有实体id使用小写英文，不能用中文名称当id。
人物knowledge只填clues字典的键，绝不能填知识原文。knowledge条件value=true，owner条件value是人物/场景ID。
只能引用asset_catalog列出的素材ID；没有放大镜素材就用已存在的道具，不能编造magnifier或placeholder。
失物仍是存在的物品：owner是实际所在的合法场景，不可用unmade假装失踪。制作产物才用unmade，recipe列真实item ID且至少两个。
找回物品的必要任务必须检查owner=player或指定伙伴，不能仅靠learn一条“找到了”的线索冒充完成。
当前状态中已拥有的知识不能再作为唯一动作后果。必要任务不要依赖一个唯一选项；提供可补救的替代路径。
叙述只能写已经确认或本次操作建立的事实，不能先写物品已转移/任务已完成，再让玩家选择是否做。
核心任务与承诺全部完成、实际已用至少三类互动、两页回响、特长真实影响行动后，才能在达到页数时结束。
图像用合法场景、在场人物与可及道具分层组合。key_art默认null，除非它的全部适用条件都已被确认。'''


def compact_context(stage, raw):
    context = deepcopy(raw)
    story = context.get('story', {})
    blueprint = context.get('blueprint') or story.get('blueprint') or {}
    cast = {c['name'] for c in blueprint.get('characters', [])} or set(context.get('selected', {}).get('cast', []))
    manifest = context.pop('manifest', None) or story.pop('manifest', {})
    if manifest:
        catalog = {'scenes':[], 'props':[], 'characters':{}, 'key_art':{}}
        for aid, spec in manifest.items():
            kind=spec['kind']
            if kind=='scene':catalog['scenes'].append(aid)
            elif kind=='prop':catalog['props'].append(aid)
            elif kind=='character' and (not cast or spec['character'] in cast):
                catalog['characters'].setdefault(spec['character'], []).append(aid)
            elif kind=='key_art' and stage not in {'concepts','blueprint','setup','setup_repair'} and set(spec.get('characters',[]))<=cast:
                catalog['key_art'][aid]={k:v for k,v in spec.items() if k in {'scenes','props','characters','conditions','event_verbs'}}
        context['asset_catalog']=catalog
    for settings in [context.get('settings',{}),story.get('settings',{})]:
        settings.pop('assets',None)
    if cast and 'character_bible' in context:
        context['character_bible']={k:v for k,v in context['character_bible'].items() if k in cast}
    if context.get('post_action_state'):
        story.pop('state',None)
    if stage in {'proposal','repair','review'} and not context.get('request',{}).get('text'):
        for page in story.get('pages',[]):
            page.pop('interactions',None)
    context['contract_notes']=GUIDE
    if stage in {'blueprint','setup','setup_repair'}:
        context['contract_notes'] += '\n蓝图：预置至少16条彼此不同的可探索线索或成果事实，以支持12页真实推进；资源time不少于24、materials不少于12。主线最多3项必需任务，每项均有可验证条件；其余设为可选。所有参与角色cast与selected完全一致，player名称与settings.character一致，同场伙伴能实际参与；故事允许移动到已有场景。arc必须等于selected.arc。'
    if stage in {'setup','setup_repair','opening'}:
        context['contract_notes'] += '\n开场页：文字须严格符合年龄字数，先呈现待解决的问题；不要在文字中提前发现尚未知的线索。至少两条当前可执行且后果不同的动作，优先观察/对话。callbacks=[]，choices=[]。'
    if stage in {'proposal','repair'}:
        context['contract_notes'] += '\n按钮请求：其结果已在post_action_state和action_events确认，resolved_action必须null。自由文字请求才需要resolved_action。新页的画面与动作根据行动之后的状态设计。不能为了凑页数重复检查已知事实或无故刷关系；用未发现的线索、不同任务推进、角色动机或新地点形成事件。callbacks优先引用已有event ID，明确回应其具体动作或讨论理由。'
    if stage=='review':
        context['contract_notes'] += '\n这是独立语义审校：只输出approved与issues，不重写正文。技术字段已由程序验证；重点检查可见文字是否提前宣布未执行的动作、目标是否真实闭合、转折是否有前因、同一角色口吻，以及画面具体对象是否与文字关键对象一致。字数或未展示的未来计划不应误报为当前事件。发现关键矛盾必须拒绝，并提出精确可修订问题。'
    return context
