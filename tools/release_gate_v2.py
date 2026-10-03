#!/usr/bin/env python3
"""Formal release gates require actual live books, human reviews and installed packages."""
import argparse,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DIMENSIONS=['coherence','fun','choice_consequences','image_consistency']
def assess(directory, comparisons, platforms):
    failures=[]
    def require(ok,reason):
        if not ok:failures.append(reason)
    manifest=json.loads((ROOT/'game/storybook/asset_manifest.json').read_text(encoding='utf-8'))['assets']
    require(all(sum(s['kind']==k for s in manifest.values())>=v for k,v in {'scene':18,'character':54,'prop':36,'key_art':12}.items()),'素材覆盖不足')
    summary=json.loads((directory/'summary.json').read_text(encoding='utf-8')) if (directory/'summary.json').exists() else {}
    require(summary.get('mode')=='live' and summary.get('books_generated')==60,'尚未完成60本真实模型生成')
    results=json.loads((directory/'results.json').read_text(encoding='utf-8')) if (directory/'results.json').exists() else []
    require(len(results)==60 and len({r['id'] for r in results})==60,'真实评测集不完整')
    from collections import Counter
    coverage=Counter((r.get('arc'),r.get('age')) for r in results)
    require(all(coverage[(arc,age)]==5 for arc in ['mystery','comedy','craft','journey','negotiation','festival'] for age in ['6-8','9-12']), '缺少六种结构、两档年龄各五本的覆盖')
    require(sum(r.get('new_theme') is True for r in results)>=30,'新主题不足评测集的一半')
    for row in results:
        path=directory/(row['id']+'.json');book=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        check=row.get('result',{})
        require(row['status']=='complete' and book.get('mock') is False and bool(book.get('usage')) and all(m.get('mock') is False for m in book.get('usage',[])),row['id']+'不是真实模型完成作品')
        require(check.get('ledger_valid') and len(check.get('interaction_types',[]))>=3 and check.get('callback_pages',0)>=2,row['id']+'缺少互动后果、回响或账本验证')
        require(check.get('cost_usd') is not None and check.get('tokens') is not None,row['id']+'缺少调用费用或token测量')
    reviews=list(csv.DictReader((directory/'human-review.csv').open(encoding='utf-8'))) if (directory/'human-review.csv').exists() else []
    require(len(reviews)==60 and {r['id'] for r in reviews}=={r['id'] for r in results},'缺少逐本人工检查')
    require(all(r.get('reviewer','').strip() and all(r.get(k)=='0' for k in ['critical_contradictions','omitted_tasks','image_object_conflicts']) for r in reviews),'人工检查尚未完成或仍有关键问题')
    pairs=list(csv.DictReader(comparisons.open(encoding='utf-8'))) if comparisons.exists() else []
    require(len(pairs)==20 and len({r.get('id') for r in pairs})==20,'缺少20组同主题盲评')
    for dimension in DIMENSIONS:
        try:
            values=[float(r[dimension]) for r in pairs]
            ok=len(values)==20 and all(1<=v<=5 for v in values) and sum(values)/20>=4
        except (ValueError,KeyError):ok=False
        require(ok,dimension+'未达到平均4分')
    require(all(r.get('reviewer','').strip() and r.get('theme','').strip() and r.get('legacy_evidence','').strip() and r.get('v2_evidence','').strip() for r in pairs),'盲评缺少审阅者或两版同主题作品证据')
    evidence=json.loads(platforms.read_text(encoding='utf-8')) if platforms.exists() else {}
    for platform in ['mac','windows','linux']:
        p=evidence.get(platform,{})
        require(p.get('verified') is True and p.get('installed_package') is True and bool(p.get('package_sha256')) and bool(p.get('evidence')),platform+'安装包未完成实际验证')
    return {'formal_release_eligible':not failures,'failures':failures}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation',type=Path,default=ROOT/'docs/v2/live-evaluation');p.add_argument('--comparisons',type=Path,default=ROOT/'docs/v2/comparison-review.csv');p.add_argument('--platforms',type=Path,default=ROOT/'docs/v2/platforms.json');p.add_argument('--output',type=Path,default=ROOT/'docs/v2/release-gate.json');a=p.parse_args()
    result=assess(a.evaluation,a.comparisons,a.platforms);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n', encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['formal_release_eligible'] else 1
if __name__=='__main__':sys.exit(main())
