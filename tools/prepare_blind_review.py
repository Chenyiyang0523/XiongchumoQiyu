#!/usr/bin/env python3
"""Prepare anonymous A/B books and decode completed human scores after review."""
import argparse
import csv
import json
import random
import shutil
from pathlib import Path
DIMENSIONS = ['coherence', 'fun', 'choice_consequences', 'image_consistency']


def prepare(pairs_path, output, seed):
    pairs = json.loads(pairs_path.read_text(encoding='utf-8'))
    if len(pairs) != 20 or len({r['id'] for r in pairs}) != 20:
        raise ValueError('需要20组不同编号的实际同主题作品')
    if (output/'scores.csv').exists():
        raise ValueError('已有评分表；请使用新目录，避免覆盖人工工作')
    for pair in pairs:
        if not pair.get('theme') or not all(Path(pair[k]).is_file() for k in ['legacy', 'v2']):
            raise ValueError('缺少同主题的实际作品：'+pair['id'])
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    mapping, rows = [], []
    for n, pair in enumerate(pairs):
        sources = [('legacy', Path(pair['legacy'])), ('v2', Path(pair['v2']))]
        rng.shuffle(sources)
        for label, (version, path) in zip(['A', 'B'], sources):
            target = output/('%02d-%s.html' % (n+1, label))
            shutil.copy2(path, target)
            mapping.append({'id':pair['id'], 'label':label, 'version':version,
                            'source':str(path), 'theme':pair['theme']})
            rows.append({'id':pair['id'], 'label':label, 'book':target.name})
    (output/'reviewer-mapping.private.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (output/'scores.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['id', 'label', 'book', 'reviewer']+DIMENSIONS+['notes'])
        w.writeheader(); w.writerows(rows)
    print('已生成40份匿名作品与评分表。映射文件须在审阅结束前由组织者保管。')


def decode(directory, output):
    mapping = json.loads((directory/'reviewer-mapping.private.json').read_text(encoding='utf-8'))
    scores = list(csv.DictReader((directory/'scores.csv').open(encoding='utf-8')))
    by_key = {(r['id'], r['label']):r for r in scores}
    if len(scores) != 40 or len(by_key) != 40:
        raise ValueError('需要40份独立的人工评分')
    pairs = {}
    for m in mapping:
        score = by_key[(m['id'], m['label'])]
        if not score['reviewer'].strip() or not all(1 <= float(score[d]) <= 5 for d in DIMENSIONS):
            raise ValueError('评分未完成：'+m['id']+' '+m['label'])
        row = pairs.setdefault(m['id'], {'id':m['id'], 'theme':m['theme']})
        row[m['version']+'_evidence'] = m['source']
        if m['version'] == 'v2':
            row.update({k:score[k] for k in ['reviewer']+DIMENSIONS+['notes']})
        else:
            row['legacy_scores'] = json.dumps({k:score[k] for k in DIMENSIONS})
    if len(pairs) != 20: raise ValueError('版本映射不完整')
    with output.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['id', 'theme', 'reviewer', 'legacy_evidence', 'v2_evidence']+DIMENSIONS+['notes', 'legacy_scores'])
        w.writeheader(); w.writerows(pairs.values())
    print('已解盲并保留两版评分。发布门禁按真实2.0作品分数判断。')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare'); a.add_argument('pairs', type=Path); a.add_argument('output', type=Path); a.add_argument('--seed', type=int, default=20261002)
    a = sub.add_parser('decode'); a.add_argument('directory', type=Path); a.add_argument('output', type=Path)
    a = p.parse_args()
    if a.command == 'prepare': prepare(a.pairs, a.output, a.seed)
    else: decode(a.directory, a.output)
if __name__ == '__main__': main()
