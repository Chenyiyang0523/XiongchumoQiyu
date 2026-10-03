#!/usr/bin/env python3
"""Consolidate explicit recovery runs without concealing failed story attempts.

Run only after corpus and recovery workers stop. All books are read from the
authoritative database and revalidated with the current engine before export.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.evaluate_books import ROOT, corpus, checks, measured_usage
from service.storage import Store
from storybook.export import export_html


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runs',type=Path,nargs='+',required=True)
    args=parser.parse_args();store=Store(args.database)
    with store.db() as db:
        if db.execute("SELECT 1 FROM jobs WHERE phase NOT IN ('complete','failed')").fetchone():
            raise ValueError('Workers still have pending jobs; consolidation must wait')
        creations=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE kind='create' AND account='evaluation' ORDER BY created")]
    history=[];runs=[]
    for directory in args.runs:
        path=directory/'results.json'
        if path.exists():
            history.extend({'run_directory':str(directory),'row':row} for row in json.loads(path.read_text(encoding='utf-8')))
        path=directory/'run-history.json'
        if path.exists():runs.extend({'directory':str(directory),**r} for r in json.loads(path.read_text(encoding='utf-8')))
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[];all_attempts=[]
    for case in corpus():
        prefix='evaluation-'+case['id']
        attempts=[]
        for creation in creations:
            if creation['ikey']!=prefix and not creation['ikey'].startswith(prefix+'-attempt-'):continue
            record={'story_id':creation['id'],'creation_key':creation['ikey'],'phase':creation['phase']}
            try:
                book=store.story(creation['id']);record.update(status=book['status'],confirmed_pages=len(book['pages']),checks=checks(book))
                record['usage']=measured_usage(store.usage(book['id']))
            except KeyError:
                record.update(status='creation_failed',error=creation['error'],usage=measured_usage(store.usage(creation['id'])))
            attempts.append(record)
        all_attempts.append({**case,'attempts':attempts})
        complete=[a for a in attempts if a['status']=='complete']
        if complete:
            # First completed attempt wins; do not cherry-pick prose or scores.
            chosen=complete[0];book=store.story(chosen['story_id']);book['usage']=store.usage(book['id'])
            json_path=args.output/(case['id']+'.json')
            json_path.write_text(json.dumps(book,ensure_ascii=False,indent=2),encoding='utf-8')
            export_html(book,args.output/(case['id']+'.html'),lambda p:(ROOT/'game'/p).read_bytes())
            rows.append({**case,'status':'complete','story_id':book['id'],'creation_key':chosen['creation_key'],
                'story_attempts':len(attempts),'result':{**checks(book),**measured_usage(book['usage'])},
                'book_sha256':hashlib.sha256(json_path.read_bytes()).hexdigest()})
        else:rows.append({**case,'status':attempts[-1]['status'] if attempts else 'not_attempted','attempts':attempts})
    metrics=[m for creation in creations for m in store.usage(creation['id'])]
    complete=sum(r['status']=='complete' for r in rows)
    first_pass=next((json.loads((d/'results.json').read_text(encoding='utf-8')) for d in args.runs if (d/'results.json').exists()),[])
    summary={'mode':'live','model':'glm-5.3','backend':'glm-local','books_generated':complete,'cases':60,'new_themes':36,
        'status':'awaiting_human_review' if complete==60 else 'technical_checks_incomplete',
        'technical_corpus_passed':complete==60,'live_release_eligible':False,'human_review_status':'pending',
        'comparison_pairs_required':20,'first_run_outcomes':dict(collections.Counter(r['status'] for r in first_pass)),
        'story_attempts':len(creations),'recovery_outcomes_preserved':True,'total_usage_all_story_attempts':measured_usage(metrics),
        'all_attempt_statuses':dict(collections.Counter(a['status'] for row in all_attempts for a in row['attempts'])),
        'human_quality_scores':None}
    for name,value in [('results.json',rows),('summary.json',summary),('all-attempts.json',all_attempts),('recovery-history.json',history),('run-history.json',runs)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    review=args.output/'human-review.csv'
    if not review.exists():
        with review.open('w',newline='',encoding='utf-8') as output:
            fields=['id','reviewer','critical_contradictions','omitted_tasks','image_object_conflicts','coherence','fun','choice_consequences','image_consistency','notes']
            writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader();writer.writerows({'id':c['id']} for c in corpus())
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if complete==60 else 1


if __name__=='__main__':sys.exit(main())
