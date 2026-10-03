#!/usr/bin/env python3
"""Real-model intention probes on independent copies of a confirmed opening.

This restores an existing real book's prefix; it is not another generated book
and does not count towards the 60-book corpus.
"""
import argparse,json,sys
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'game')]
from service.storage import Store
from service.pipeline import Pipeline
from service.provider import create_provider
from service.models import SubmitRequest
from storybook.engine import replay
from tools.evaluate_books import measured_usage

PROBES=[
 ('negation','先不去山洞，也不拿蜂蜜罐。我想留在树洞旁看看地上的脚印。'),
 ('creative_use','不追脚印。我想用背包里的小灯笼照亮树洞边的泥地，看看暗处有没有留下痕迹。'),
 ('ambiguous','把它给他。'),
 ('unavailable','我现在就把还在山洞里的蜂蜜罐交给熊二，留在树洞旁，不去山洞，也不请人送来。')]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.local/glm/action-probes')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    source=json.loads((ROOT/'docs/v2/examples/real-glm-book.json').read_text(encoding='utf-8'))
    assert source['mock'] is False
    store=Store(args.output/'probes.sqlite');pipeline=Pipeline(store,create_provider());rows=[]
    for name,text in PROBES:
        opening=deepcopy(source);opening.update(events=[],pages=opening['pages'][:1],ending=None,status='active',usage=[])
        opening['state']=deepcopy(opening['pages'][0]['state_snapshot'])
        opening['pages'][0]['choices']=[];opening['pages'][0].pop('discussion',None)
        replay(opening)
        jid=store.enqueue('live-probes','create',{'idempotency_key':'confirmed-prefix-'+name})
        opening['id']=jid;store.commit({'id':jid,'kind':'create','account':'live-probes'},opening)
        req=SubmitRequest(version=1,idempotency_key='intention-'+name,text=text).model_dump()
        turn=store.enqueue('live-probes','turn',req,jid);pipeline.process(store.next_job())
        job=store.job(turn);after=store.story(jid)
        row={'id':name,'input':text,'source':'restored confirmed opening of a real GLM book','mock':False,
             'phase':job['phase'],'error':job['error'],'usage':measured_usage(store.usage(jid))}
        result=job.get('result') or {}
        row['clarifications']=result.get('clarification',[])
        unchanged=after['state']==opening['state']
        if name=='ambiguous':
            row['passed']=job['phase']=='complete' and len(row['clarifications'])>=2 and unchanged
        elif name=='unavailable':
            row['passed']=unchanged and (bool(row['clarifications']) or job['phase']=='failed')
        else:
            row['passed']=job['phase']=='complete' and not row['clarifications'] and after['state']['location']==opening['state']['location'] and after['state']['items']['item.honey']==opening['state']['items']['item.honey']
            if name=='creative_use':
                action_events=after['events'];row['passed']=row['passed'] and any(e['verb']=='use' for e in action_events)
        row['events']=after['events'];replay(after);row['ledger_valid']=True
        (args.output/(name+'.book.json')).write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append(row);(args.output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,row['phase'],'passed='+str(row['passed']),flush=True)
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__':raise SystemExit(main())
