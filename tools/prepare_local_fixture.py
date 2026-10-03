"""Build an explicitly mocked, validated collect-then-craft UI test page."""
import json
from copy import deepcopy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'game')]
from service.mock import blueprint,page,action,effect,condition
from service.models import StoryBlueprint,BookPage
from storybook.engine import initial_state,validate_page

def prepare(destination):
    manifest=json.loads((ROOT/'game/storybook/asset_manifest.json').read_text(encoding='utf-8'))['assets']
    settings={'theme':'合作做小旗','character':'熊大','age':'6-8','pages':8,'parent_mode':False,'assets':list(manifest)}
    b=blueprint(settings,'craft');b.update(goal='合作做一面醒目的小旗',promises={})
    b['items']+=[{'id':'item.wood','name':'木板','asset':'prop.plank','owner':'scene.forest'},
        {'id':'item.string','name':'绳子','asset':'prop.rope','owner':'scene.forest'},
        {'id':'item.flag','name':'小旗','asset':'prop.flag','owner':'unmade','recipe':['item.wood','item.string']}]
    b['quests']=[{'id':'quest.flag','title':'做出小旗','conditions':[condition('owner','item.flag','player')]}]
    b=StoryBlueprint.model_validate(b).model_dump();state=initial_state(b,manifest)
    p=page(1,b,state,settings,manifest,[])
    p.update(title='先收材料，再组合',text='森林小路的岔口有点难找。熊大和赵琳想做一面醒目的小旗，让伙伴们一眼就能看见集合点。地上放着一块轻木板和一卷绳子。先把两样材料收进背包，再把它们牢牢扎在一起，试试小旗能不能立稳吧。')
    p['illustration']['props']=['prop.plank','prop.rope']
    collect=action('action.collect','observe','收好木板和绳子','item.wood',[
        effect('transfer','item.wood','player'),effect('transfer','item.string','player')],'两样材料都收进了背包。')
    make=action('action.make','combine','组合成小旗','item.wood',[effect('craft','item.flag',True)],'你把木板和绳子扎成了小旗。',inputs=['item.wood','item.string'])
    p['interactions']=[{'id':'inter.collect','kind':'observe','instruction':'先收集材料','actions':[collect]},
        {'id':'inter.make','kind':'items','instruction':'材料齐了再组合','actions':[make]}]
    p=BookPage.model_validate(p).model_dump();validate_page(p,state,b,manifest,[],settings['assets'],settings['age'])
    p['state_snapshot']=deepcopy(state)
    book={'schema_version':2,'id':'qa-local-operations','settings':settings,'blueprint':b,'initial_blueprint':deepcopy(b),
        'state':state,'events':[],'pages':[p],'manifest':manifest,'ending':None,'status':'active','mock':True,'usage':[]}
    Path(destination).write_text(json.dumps(book,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':prepare(sys.argv[1])
