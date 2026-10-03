import csv
import json
from pathlib import Path
import pytest
from tools.release_gate_v2 import assess
from tools.prepare_blind_review import prepare, decode, DIMENSIONS


def test_mock_corpus_cannot_pass_formal_release_gate(tmp_path):
    (tmp_path/'summary.json').write_text(json.dumps({'mode':'mock','books_generated':60}))
    result=assess(tmp_path,tmp_path/'pairs.csv',tmp_path/'platforms.json')
    assert result['formal_release_eligible'] is False
    assert '尚未完成60本真实模型生成' in result['failures']
    assert '缺少逐本人工检查' in result['failures']
    assert 'windows安装包未完成实际验证' in result['failures']


def test_blind_review_hides_versions_preserves_work_and_decodes_scores(tmp_path):
    legacy=tmp_path/'old.html';new=tmp_path/'new.html'
    legacy.write_text('<html>旧故事</html>');new.write_text('<html>新故事</html>')
    pairs=tmp_path/'pairs.json';output=tmp_path/'blind'
    pairs.write_text(json.dumps([{'id':str(i),'theme':'音乐会','legacy':str(legacy),'v2':str(new)} for i in range(20)]))
    prepare(pairs,output,7)
    rows=list(csv.DictReader((output/'scores.csv').open()))
    assert len(rows)==40 and not ({'legacy_evidence','v2_evidence','version'} & set(rows[0]))
    with pytest.raises(ValueError):prepare(pairs,output,7)
    with pytest.raises(ValueError):decode(output,tmp_path/'decoded.csv')
    mapping={(r['id'],r['label']):r['version'] for r in json.loads((output/'reviewer-mapping.private.json').read_text())}
    for r in rows:
        r['reviewer']='人工测试审阅者'
        for d in DIMENSIONS:r[d]='4' if mapping[(r['id'],r['label'])]=='v2' else '2'
    with (output/'scores.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    decode(output,tmp_path/'decoded.csv')
    decoded=list(csv.DictReader((tmp_path/'decoded.csv').open()))
    assert len(decoded)==20 and all(r['fun']=='4' and json.loads(r['legacy_scores'])['fun']=='2' for r in decoded)
