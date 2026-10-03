"""Compile model-authored intentions into the canonical, strictly checked protocol.

The model writes story-specific facts and consequences. Identity envelopes, effect
syntax and display asset bindings are deterministic; the reducer remains authority.
"""
from copy import deepcopy
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
    recipe:list[str]=Field(default_factory=list)

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
    locations:dict[str,str]=Field(default_factory=dict)
    initial_knowledge:dict[str,list[str]]=Field(default_factory=dict)
    resources:dict[str,int]=Field(default_factory=lambda:{'time':24,'materials':12})
    promises:dict[str,bool]=Field(default_factory=dict)
    twists:list[str]=Field(default_factory=list)
    closure:str
    solution_tag:str

class ModelAction(Contract):
    id:str
    label:str
    verb:Verb
    target:str
    feedback:str
    learn:list[str]=Field(default_factory=list)
    move:dict[str,str]=Field(default_factory=dict)
    take:list[str]=Field(default_factory=list)
    give:dict[str,str]=Field(default_factory=dict)
    consume:list[str]=Field(default_factory=list)
    craft:list[str]=Field(default_factory=list)
    spend:dict[str,int]=Field(default_factory=dict)
    relationships:dict[str,int]=Field(default_factory=dict)
    promises:dict[str,bool]=Field(default_factory=dict)
    inputs:list[str]=Field(default_factory=list)
    trait:TraitUse|None=None
    hotspot:str|None=None

class ModelInteraction(Contract):
    id:str
    kind:str
    instruction:str
    actions:list[ModelAction]
    order:list[str]=Field(default_factory=list)
    order_action:str|None=None

class ModelPage(Contract):
    id:str
    title:str
    text:str
    characters:dict[str,str]=Field(default_factory=dict,description='人物ID到表情名：calm/happy/thinking/surprised/worried/determined')
    items:list[str]=Field(default_factory=list,description='画面出现的物品ID，必须存在且可及')
    interactions:list[ModelInteraction]
    callbacks:list[str]=Field(default_factory=list)

class ModelOpening(Contract):
    blueprint:ModelBlueprint
    page:ModelPage

class ModelEvent(Contract):
    id:str
    cause:list[str]
    description:str
    move:dict[str,str]=Field(default_factory=dict)
    learn:dict[str,list[str]]=Field(default_factory=dict)

class ModelExpansion(Contract):
    items:list[ModelItem]=Field(default_factory=list,max_length=4)
    clues:dict[str,str]=Field(default_factory=dict,max_length=4)
    tasks:list[ModelTask]=Field(default_factory=list,max_length=2)

class ModelTurn(Contract):
    page:ModelPage|None=None
    events:list[ModelEvent]=Field(default_factory=list,max_length=3)
    action:ModelAction|None=None
    clarification:list[ModelAction]=Field(default_factory=list,max_length=3)
    ending:Ending|None=None
    expansion:ModelExpansion|None=None

def roles(settings,selected):
    return {('player' if name==settings['character'] else 'npc.'+SLUGS[name]):name for name in selected['cast']}

def task(value):
    conditions=[]
    conditions += [{'kind':'knowledge','key':k,'value':True} for k in value['knowledge']]
    conditions += [{'kind':'owner','key':k,'value':v} for k,v in value['owners'].items()]
    conditions += [{'kind':'relationship','key':k,'value':v,'comparison':'gte'} for k,v in value['relationships'].items()]
    conditions += [{'kind':'promise','key':k,'value':True} for k in value['promises']]
    return {k:value[k] for k in ['id','title','required','dependencies']}|{'conditions':conditions}

def blueprint(value,settings,selected):
    mapping=roles(settings,selected)
    if set(value['profiles'])!=set(mapping):raise ValueError('profiles must use exactly the provided role IDs')
    return {k:deepcopy(value[k]) for k in ['title','goal','conflict','clues','items','resources','promises','twists','closure','solution_tag']}|{
        'schema_version':2,'theme':settings['theme'],'arc':selected['arc'],
        'characters':[{'id':cid,'name':name,'location':value['locations'].get(cid,value['scene']),
            'knowledge':value['initial_knowledge'].get(cid,[]),**value['profiles'][cid]} for cid,name in mapping.items()],
        'quests':[task(t) for t in value['tasks']]}

def action(value,state):
    changes=[]
    changes += [{'op':'learn','target':k,'value':True} for k in value['learn']]
    changes += [{'op':'move','target':k,'value':v} for k,v in value['move'].items()]
    changes += [{'op':'transfer','target':k,'value':'player'} for k in value['take']]
    changes += [{'op':'transfer','target':k,'value':v} for k,v in value['give'].items()]
    changes += [{'op':'consume','target':k,'value':True} for k in value['consume']]
    changes += [{'op':'craft','target':k,'value':True} for k in value['craft']]
    if any(type(v)!=int or v<=0 for v in value['spend'].values()):raise ValueError('spend amounts must be positive integers')
    changes += [{'op':'resource','target':k,'value':-v} for k,v in value['spend'].items()]
    changes += [{'op':'relationship','target':k,'value':v} for k,v in value['relationships'].items()]
    changes += [{'op':'promise','target':k,'value':v} for k,v in value['promises'].items()]
    result={k:value[k] for k in ['id','label','verb','target','feedback','inputs']}
    result.update(effects=changes,prerequisites=[],alternatives=[],trait_use=value['trait'])
    if value['hotspot']:
        target=value['hotspot']
        result['hotspot']=state['items'][target]['asset'] if target in state['items'] else target
    return result

def page(value,state,manifest):
    characters={}
    for cid,mood in value['characters'].items():
        if cid not in state['characters']:raise ValueError('unknown pictured character')
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
    interactions=[]
    for inter in value['interactions']:
        interactions.append({k:deepcopy(inter[k]) for k in ['id','kind','instruction','order','order_action']}|
            {'actions':[action(a,state) for a in inter['actions']]})
    return {k:deepcopy(value[k]) for k in ['id','title','text','callbacks']}|{
        'schema_version':2,'choices':[], 'illustration':{'scene':state['location'],'characters':characters,
            'props':list(dict.fromkeys(state['items'][i]['asset'] for i in value['items'])),'key_art':None},
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
    return {'schema_version':2,'page':page(value['page'],state,manifest) if value['page'] else None,
            'events':events,'resolved_action':resolved,'clarification':[action(a,state) for a in value['clarification']],
            'ending':value['ending'],'expansion':expansion}
