"""Compile model-authored intentions into the canonical, strictly checked protocol.

The model writes story-specific facts and consequences. Identity envelopes, effect
syntax and display asset bindings are deterministic; the reducer remains authority.
"""
from copy import deepcopy
import hashlib
import json
from typing import Literal
from pydantic import Field
from service.models import Contract, Ending, TraitUse, Arc, Verb

SLUGS={'光头强':'guangtouqiang','熊大':'xiongda','熊二':'xionger','吉吉国王':'jijiguowang',
       '毛毛':'maomao','赵琳':'zhaolin','天才威':'tiancaiwei','大马猴':'damahou','二狗':'ergou'}

class Profile(Contract):
    motivation:str
    strength:str
    weakness:str

class ModelItem(Contract):
    id:str
    name:str
    asset:str
    owner:str
    recipe:list[str]=Field(default_factory=list,description='制作原料的已声明item ID，绝不是prop素材ID；仅owner=unmade的产物填写')

class ModelTask(Contract):
    id:str
    title:str
    required:bool=True
    knowledge:list[str]=Field(default_factory=list)
    owners:dict[str,str]=Field(default_factory=dict)
    relationships:dict[str,int]=Field(default_factory=dict)
    promises:list[str]=Field(default_factory=list)
    dependencies:list[str]=Field(default_factory=list)

class ModelBlueprint(Contract):
    title:str
    goal:str
    conflict:str
    scene:str
    profiles:dict[str,Profile]
    clues:dict[str,str]
    items:list[ModelItem]=Field(default_factory=list)
    tasks:list[ModelTask]
    locations:dict[str,str]=Field(default_factory=dict,description='人物ID到场景ID，省略时人物都在scene；不是场景到中文名称')
    initial_knowledge:dict[str,list[str]]=Field(default_factory=dict)
    resources:dict[str,int]=Field(default_factory=lambda:{'time':24,'materials':12})
    promises:dict[str,bool]=Field(default_factory=dict)
    promise_descriptions:dict[str,str]=Field(default_factory=dict,description='每个承诺ID对应具体约定与可验证的兑现办法，键与promises完全一致')
    twists:list[str]=Field(default_factory=list)
    closure:str
    solution_tag:str

class ModelAction(Contract):
    id:str
    label:str
    verb:Verb
    target:str=Field(description='observe取物时指可及item；use指已拥有物品；combine指配方产物或原料，但inputs原料必须已拥有或由本页另一卡片收集；ask/negotiate指在场人物；allocate指资源')
    feedback:str
    learn:list[str]=Field(default_factory=list)
    move:dict[str,str]=Field(default_factory=dict,description='人物ID到场景ID，如 {player: scene.bridge}；键不能是场景或中文名称')
    take:list[str]=Field(default_factory=list)
    give:dict[str,str]=Field(default_factory=dict,description='物品ID到接收人物ID或当前场景ID；可交给在场伙伴，也可把物品放在当前地点，不能隔空放置')
    consume:list[str]=Field(default_factory=list)
    craft:list[str]=Field(default_factory=list)
    spend:dict[str,int]=Field(default_factory=dict)
    relationships:dict[str,int]=Field(default_factory=dict)
    promises:dict[str,bool]=Field(default_factory=dict)
    inputs:list[str]=Field(default_factory=list)
    trait:TraitUse|None=None
    hotspot:str|None=Field(default=None,description='画面page.items中一个已声明的item ID；没有对应道具时省略，不写中文描述')

class ModelInteraction(Contract):
    id:str
    kind:Literal['observe','evidence','items','dialogue','allocation']
    instruction:str
    actions:list[ModelAction]=Field(min_length=1,max_length=4)
    order:list[str]=Field(default_factory=list,description='已发现线索的稳定ID数组，不是中文线索文本；没有排序时留空')
    order_action:str|None=None

class ModelPage(Contract):
    id:str
    title:str
    text:str
    characters:dict[str,str]=Field(default_factory=dict,max_length=4,description='人物ID到表情名：calm/happy/thinking/surprised/worried/determined')
    items:list[str]=Field(default_factory=list,max_length=6,description='画面出现的物品ID，必须存在且可及，消耗或未制作物品不能出现')
    interactions:list[ModelInteraction]=Field(min_length=1,max_length=2)
    callbacks:list[str]=Field(default_factory=list)
    key_art:str|None=None

class ModelOpening(Contract):
    blueprint:ModelBlueprint
    page:ModelPage

class ModelEvent(Contract):
    id:str=Field(description='新NPC事件的唯一ID，不能重复action_events中已执行的玩家事件')
    cause:list[str]=Field(description='已存在的event ID数组，不能填page、action ID或中文')
    description:str
    move:dict[str,str]=Field(default_factory=dict,description='已有NPC ID到场景ID，不能用场景作键或移动player')
    learn:dict[str,list[str]]=Field(default_factory=dict,description='已有NPC ID到线索ID数组，禁止修改player认知')

class ModelExpansion(Contract):
    items:list[ModelItem]=Field(default_factory=list,max_length=4)
    clues:dict[str,str]=Field(default_factory=dict,max_length=4)
    tasks:list[ModelTask]=Field(default_factory=list,max_length=2)

class ModelTurn(Contract):
    page:ModelPage|None
    events:list[ModelEvent]=Field(max_length=3,description='通常留空[]；action_events已确认按钮后果，不要重复输出。仅有额外NPC移动/获知信息才新增。')
    action:ModelAction|None
    clarification:list[ModelAction]=Field(max_length=3)
    ending:Ending|None
    expansion:ModelExpansion|None

def roles(settings,selected):
    return {('player' if name==settings['character'] else 'npc.'+SLUGS[name]):name for name in selected['cast']}

def task(value):
    conditions=[]
    conditions += [{'kind':'knowledge','key':k,'value':True} for k in value['knowledge']]
    conditions += [{'kind':'owner','key':k,'value':v} for k,v in value['owners'].items()]
    conditions += [{'kind':'relationship','key':k,'value':v,'comparison':'gte'} for k,v in value['relationships'].items()]
    conditions += [{'kind':'promise','key':k,'value':True} for k in value['promises']]
    return {k:value[k] for k in ['id','title','required','dependencies']}|{'conditions':conditions}

def character_reference(key,state):
    if key in state['characters']:return key
    names={key}
    if key.startswith('npc.'):
        names.update(name for name,slug in SLUGS.items() if key=='npc.'+slug)
    found=[cid for cid,c in state['characters'].items() if c['name'] in names]
    if len(found)==1:return found[0]
    raise ValueError('unknown or ambiguous character reference '+key)

def blueprint(value,settings,selected):
    mapping=roles(settings,selected)
    if set(value['profiles'])!=set(mapping):raise ValueError('profiles must use exactly the provided role IDs')
    if set(value['promise_descriptions'])!=set(value['promises']):
        raise ValueError('every promise needs a concrete description and fulfilment condition')
    return {k:deepcopy(value[k]) for k in ['title','goal','conflict','clues','items','resources','promises','twists','closure','solution_tag']}|{
        'promise_descriptions':deepcopy(value['promise_descriptions']),
        'schema_version':2,'theme':settings['theme'],'arc':selected['arc'],
        'characters':[{'id':cid,'name':name,'location':value['locations'].get(cid,value['scene']),
            'knowledge':value['initial_knowledge'].get(cid,[]),**value['profiles'][cid]} for cid,name in mapping.items()],
        'quests':[task(t) for t in value['tasks']]}

def action(value,state):
    def character_id(key):
        return character_reference(key,state)
    changes=[]
    changes += [{'op':'learn','target':k,'value':True} for k in value['learn']]
    changes += [{'op':'transfer','target':k,'value':'player'} for k in value['take']]
    changes += [{'op':'craft','target':k,'value':True} for k in value['craft']]
    changes += [{'op':'transfer','target':k,'value':v if v==state['location'] else character_id(v)} for k,v in value['give'].items()]
    changes += [{'op':'consume','target':k,'value':True} for k in value['consume']]
    if any(type(v)!=int or v<=0 for v in value['spend'].values()):raise ValueError('spend amounts must be positive integers')
    changes += [{'op':'resource','target':k,'value':-v} for k,v in value['spend'].items()]
    changes += [{'op':'relationship','target':character_id(k),'value':v} for k,v in value['relationships'].items()]
    changes += [{'op':'promise','target':k,'value':v} for k,v in value['promises'].items()]
    # Take/use the accessible item before leaving its scene. This is one atomic
    # action; doing movement first would incorrectly make the same item remote.
    changes += [{'op':'move','target':character_id(k),'value':v} for k,v in value['move'].items()]
    result={k:value[k] for k in ['id','label','verb','target','feedback','inputs']}
    trait=deepcopy(value['trait'])
    if trait:trait['character']=character_id(trait['character'])
    if value['verb'] in {'ask','negotiate'}:result['target']=character_id(result['target'])
    result.update(effects=changes,prerequisites=[],alternatives=[],trait_use=trait)
    if value['hotspot']:
        target=value['hotspot']
        result['hotspot']=state['items'][target]['asset'] if target in state['items'] else target
    return result

def page(value,state,manifest):
    if sum(len(i['actions']) for i in value['interactions'])<2:
        raise ValueError('page must offer at least two consequential approaches')
    characters={}
    for cid,mood in value['characters'].items():
        cid=character_reference(cid,state)
        if cid in characters:raise ValueError('duplicate pictured character identity')
        # Rendering follows confirmed presence, as it follows client layout.
        # Omitting an off-scene decoration cannot move an entity. The semantic
        # reviewer still rejects prose that claims that absent entity acted here.
        if state['characters'][cid]['location']!=state['location']:continue
        if mood in manifest:
            if manifest[mood].get('character')!=state['characters'][cid]['name']:
                raise ValueError('wrong character sprite')
            characters[cid]=mood
            continue
        name=state['characters'][cid]['name'];suffix='normal' if mood=='calm' else mood
        aid='character.'+SLUGS[name]+'.'+suffix
        # Asset IDs are resolved from the manifest, never invented by a generator.
        matches=[k for k,s in manifest.items() if s.get('character')==name and (k.endswith('.'+mood) or k.endswith('.'+suffix))]
        if aid not in manifest:
            if len(matches)!=1:raise ValueError('unknown character expression '+mood)
            aid=matches[0]
        characters[cid]=aid
    for iid in value['items']:
        if iid not in state['items']:raise ValueError('unknown pictured item')
    visible=[iid for iid in value['items'] if state['items'][iid]['owner'] in {'player',state['location']}
             or state['items'][iid]['owner'] in state['characters'] and state['characters'][state['items'][iid]['owner']]['location']==state['location']]
    # A hotspot explicitly requests a rendered, confirmed physical instance.
    # Binding it here avoids a contradictory model-authored decoration list;
    # inaccessible/unknown objects still cannot be made visible or operable.
    for interaction in value['interactions']:
        for option in interaction['actions']:
            iid=option.get('hotspot')
            if iid in state['items']:
                owner=state['items'][iid]['owner']
                accessible=owner in {'player',state['location']} or owner in state['characters'] and state['characters'][owner]['location']==state['location']
                if accessible and iid not in visible:visible.append(iid)
    interactions=[]
    for inter in value['interactions']:
        interactions.append({k:deepcopy(inter[k]) for k in ['id','kind','instruction','order','order_action']}|
            {'actions':[action(a,state) for a in inter['actions']]})
    return {k:deepcopy(value[k]) for k in ['id','title','text','callbacks']}|{
        'schema_version':2,'choices':[], 'illustration':{'scene':state['location'],'characters':characters,
            'props':list(dict.fromkeys(state['items'][i]['asset'] for i in visible)),'key_art':value['key_art']},
        'interactions':interactions}

def turn(value,source,request,manifest):
    from storybook.engine import apply_operations, effects, expand_world
    working=deepcopy(source);state,_=apply_operations(working,request['operations'],request.get('reason',''))
    expansion=None
    if value['expansion']:
        expansion={k:deepcopy(value['expansion'][k]) for k in ['items','clues']}|{'quests':[task(t) for t in value['expansion']['tasks']]}
        expand_world(working['state'],working['blueprint'],expansion,manifest,'compilation')
        state,_=apply_operations(working,request['operations'],request.get('reason',''))
    resolved=action(value['action'],state) if value['action'] else None
    if resolved:
        effects(state,resolved,working['blueprint'],manifest,'compilation')
    events=[]
    for e in value['events']:
        changes=[{'op':'move','target':cid,'value':loc} for cid,loc in e['move'].items()]
        changes += [{'op':'learn','target':clue,'value':True,'actor':cid} for cid,clues in e['learn'].items() for clue in clues]
        event={k:deepcopy(e[k]) for k in ['id','cause','description']}|{'schema_version':2,'turn':state['version']+1,
            'action_id':e['id'],'verb':'observe','effects':changes,'reason':'','trait_use':None,'interaction_kind':None,'expansion':None}
        effects(state,{'verb':'observe','target':'player','effects':changes},working['blueprint'],manifest,'compilation')
        events.append(event)
    clarification=[action(a,state) for a in value['clarification']]
    # An informational question is not an executable interpretation. Preserve
    # the concrete alternatives, each still checked by the canonical reducer.
    clarification=[a for a in clarification if a['effects']]
    if value['clarification'] and len(clarification)<2:
        raise ValueError('clarification needs two concrete executable meanings; keep action/page null and do not guess')
    known={a['id']:a for i in source['pages'][-1]['interactions'] for a in i['actions']}
    for candidate in clarification+([resolved] if resolved else []):
        if candidate['id'] in known and candidate!=known[candidate['id']]:
            # A newly understood intention cannot redefine an existing button.
            # Give its full meaning a deterministic ID in a separate namespace.
            digest=hashlib.sha256(json.dumps({'story':source['id'],'version':source['state']['version'],'action':candidate},sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
            candidate['id']='intent.'+digest
    ending=deepcopy(value['ending'])
    if ending:
        ending['helped']=[character_reference(key,state) for key in ending['helped']]
    return {'schema_version':2,'page':page(value['page'],state,manifest) if value['page'] else None,
            'events':events,'resolved_action':resolved,'clarification':clarification,
            'ending':ending,'expansion':expansion}
