#!/usr/bin/env python3
"""Technical acceptance is separate from the deferred human release decision."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'game')]
from tools.evaluate_books import corpus, checks
from storybook.engine import can_close


def assess(directory, platforms):
    failures=[]
    expected={c['id']:c for c in corpus()}
    path=directory/'results.json'
    rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    if len(rows)!=60 or {r['id'] for r in rows}!=set(expected):failures.append('真实评测集必须完整覆盖60个指定案例')
    verified=0
    for row in rows:
        cid=row['id'];definition=expected.get(cid,{})
        if any(row.get(k)!=definition.get(k) for k in ['theme','age','arc','character','new_theme']):
            failures.append(cid+':案例参数变化');continue
        try:
            book=json.loads((directory/(cid+'.json')).read_text(encoding='utf-8'))
            if row['status']!='complete' or book.get('mock') is not False or not book.get('ending'):
                raise ValueError('不是已完成的真实作品')
            if not book.get('usage') or any(m.get('mock') is not False for m in book['usage']):
                raise ValueError('缺少真实模型调用证据')
            result=checks(book)
            if len(result['interaction_types'])<3 or result['callback_pages']<2:raise ValueError('互动类型或后续回应不足')
            if not can_close(book['state'],book['blueprint']):raise ValueError('必要任务或承诺未兑现')
            if not any(e.get('trait_use') for e in book['events']):raise ValueError('角色特征没有影响实际行动')
            if not book['settings']['pages']<=len(book['pages'])<=book['settings']['pages']+2:raise ValueError('实际长度超出规划及收束上限')
            if not (directory/(cid+'.html')).exists():raise ValueError('缺少离线导出')
            verified+=1
        except (OSError,ValueError,KeyError) as exc:failures.append(cid+':'+str(exc)[:180])
    evidence=json.loads(platforms.read_text(encoding='utf-8')) if platforms.exists() else {}
    for name in ['mac','windows','linux']:
        item=evidence.get(name,{})
        if not(item.get('verified') is True and item.get('installed_package') is True and item.get('assertions_passed',0)>=24 and item.get('package_sha256')):
            failures.append(name+':缺少实际安装包的24项通过证据')
    return {'technical_corpus_and_platforms_passed':not failures,'live_books_verified':verified,
            'human_review_status':'pending','blind_review_status':'pending','formal_release_eligible':False,
            'failures':failures,'monetary_cost':'unknown unless independently supplied; not zero'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation',type=Path,default=ROOT/'docs/v2/acceptance-evaluation')
    parser.add_argument('--platforms',type=Path,default=ROOT/'docs/v2/platforms.json')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/v2/technical-gate.json')
    args=parser.parse_args();result=assess(args.evaluation,args.platforms)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['technical_corpus_and_platforms_passed'] else 1


if __name__=='__main__':sys.exit(main())
