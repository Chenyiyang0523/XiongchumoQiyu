#!/usr/bin/env python3
"""Reproducible 60-book corpus. Fixture runs can never satisfy live release gates."""
import argparse
import csv
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'game')]
from service.models import CreateRequest, SubmitRequest
from service.storage import Store
from service.pipeline import Pipeline
from service.provider import create_provider
from service.mock import MockProvider
from storybook.engine import replay, apply_operations
from storybook.export import export_html

NEW_THEMES={
 'mystery':['不见的风铃','湖畔的脚印','树屋里的来信'],
 'comedy':['吉吉的反向指挥牌','光头强的错位野餐','集市上的同名礼物'],
 'craft':['小木桥修理队','会转弯的风筝','雨天的移动书架'],
 'journey':['竹林的回声地图','萤火虫营地','果园里的新路'],
 'negotiation':['树屋的使用约定','谁来守护幼苗','伙伴们的野餐分工'],
 'festival':['森林音乐会','湖边灯笼节','运动场的友谊赛']}
CAST=['熊大','熊二','光头强','吉吉国王','毛毛','赵琳','天才威','大马猴','二狗']

def corpus():
    cases=[]
    for n,(arc,new) in enumerate(NEW_THEMES.items()):
        old=['森林探险','寻宝之旅'] if n%2==0 else ['拯救行动','友谊考验']
        for age in ['6-8','9-12']:
            for index,theme in enumerate(old+new):
                cases.append({'id':'case.%02d'%(len(cases)+1),'arc':arc,'age':age,'theme':theme,'character':CAST[len(cases)%9],'new_theme':index>=2})
    return cases

def op(page, index=0):
    inter=page['interactions'][0]
    a=inter['actions'][index%len(inter['actions'])]
    result={'action_id':a['id'],'items':a.get('inputs',[])}
    if inter.get('order_action')==a['id']:result['order']=inter['order']
    if a['verb']=='allocate':result['amount']=-next(e['value'] for e in a['effects'] if e['op']=='resource')
    return result

def execute(pipeline,account,kind,request,sid=None):
    jid=pipeline.store.enqueue(account,kind,request,sid)
    job=pipeline.store.job(jid)
    if job['phase'] not in {'complete','failed'}:
        raw=dict(job);raw['request']=json.dumps(job['request']);raw['metrics']=json.dumps(job['metrics'])
        pipeline.process(raw)
    job=pipeline.store.job(jid)
    if job['phase']!='complete':raise ValueError(job['error'])
    if job['result'].get('clarification'):raise ValueError('scripted action unexpectedly requires clarification')
    return pipeline.store.story(job['result']['story_id'])

def checks(story):
    replay(story)
    used={e['interaction_kind'] for e in story['events'] if e.get('interaction_kind')}
    for page in story['pages']:
        chosen={c['action_id'] for c in page['choices']}
        used.update(i['kind'] for i in page['interactions'] if any(a['id'] in chosen for a in i['actions']))
    return {'completed':bool(story['ending']),'interaction_types':sorted(used),
            'callback_pages':sum(bool(p['callbacks']) for p in story['pages']),
            'ledger_valid':True,'human_checked':False,'critical_contradictions':None,
            'omitted_tasks':None,'image_object_conflicts':None}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['live','mock'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pages',type=int,choices=[8,12,16,20],default=12)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    cases=corpus()
    (args.output/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2), encoding='utf-8')
    try:provider=create_provider() if args.mode=='live' else MockProvider()
    except ValueError:
        (args.output/'summary.json').write_text(json.dumps({'mode':args.mode,'live_release_eligible':False,'status':'configuration_required','books_generated':0},indent=2), encoding='utf-8')
        print('未运行真实生成：请在本机配置 XCMQY_LLM_ENDPOINT、XCMQY_LLM_MODEL、XCMQY_LLM_KEY。',file=sys.stderr)
        return 2
    store=Store(args.output/'evaluation.sqlite')
    pipeline=Pipeline(store,provider)
    rows=[]
    for case in cases:
        start=time.monotonic()
        try:
            settings={k:case[k] for k in ['theme','character','age','arc']}
            settings.update(pages=args.pages,assets=list(pipeline.manifest),parent_mode=True)
            req=CreateRequest(settings=settings,idempotency_key='evaluation-'+case['id']).model_dump()
            story=execute(pipeline,'evaluation','create',req)
            while story['status']=='active':
                req=SubmitRequest(version=story['state']['version'],idempotency_key='evaluation-'+case['id']+'-turn-'+str(story['state']['version']),
                                  operations=[op(story['pages'][-1],int(case['id'].split('.')[1])%2)],reason='我们先核对事实，再和伙伴讨论。').model_dump()
                story=execute(pipeline,'evaluation','turn',req,story['id'])
            result=checks(story)
            (args.output/(case['id']+'.json')).write_text(json.dumps(story,ensure_ascii=False,indent=2), encoding='utf-8')
            export_html(story,args.output/(case['id']+'.html'),lambda p:(ROOT/'game'/p).read_bytes())
            metrics=story['usage']
            result.update(calls=len(metrics),tokens=None if any(not m.get('usage_known',m.get('mock',False)) for m in metrics) else sum(m['input_tokens']+m['output_tokens'] for m in metrics),
                revisions=sum(m['stage']=='repair' for m in metrics),model_wait_seconds=round(sum(m.get('seconds',0) for m in metrics),3),cost_usd=None if any(m['cost_usd'] is None for m in metrics) else sum(m['cost_usd'] for m in metrics))
            row={**case,'result':result,'status':'complete' if result['completed'] else 'continued'}
        except Exception as exc:
            row={**case,'status':'failed','error':str(exc)[:400]}
        row['seconds']=round(time.monotonic()-start,3)
        rows.append(row)
        (args.output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2), encoding='utf-8')
        print(case['id'],row['status'],flush=True)
    review_path=args.output/'human-review.csv'
    previous={r['id']:r for r in csv.DictReader(review_path.open(encoding='utf-8'))} if review_path.exists() else {}
    with review_path.open('w',newline='', encoding='utf-8') as output:
        columns=['id','reviewer','critical_contradictions','omitted_tasks','image_object_conflicts','coherence','fun','choice_consequences','image_consistency','notes']
        writer=csv.DictWriter(output,fieldnames=columns);writer.writeheader()
        writer.writerows(previous.get(c['id'],{'id':c['id']}) for c in cases)
    summary={'mode':args.mode,'status':'awaiting_human_review' if args.mode=='live' else 'fixture_only',
             'books_generated':sum(r['status']=='complete' for r in rows),'cases':60,'new_themes':36,
             'live_release_eligible':False,'comparison_pairs_required':20,'platforms_verified':[]}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2), encoding='utf-8')
    return 0 if summary['books_generated']==60 else 1
if __name__=='__main__':sys.exit(main())
