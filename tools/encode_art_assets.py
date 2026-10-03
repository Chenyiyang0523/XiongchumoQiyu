#!/usr/bin/env python3
"""Lossless container encoding only: no resizing, retouching or alpha modification."""
import json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def main():
    source=ROOT/'game/images/v2'; archive=ROOT/'assets-source/v2/raw';archive.mkdir(parents=True,exist_ok=True)
    records=[]
    for path in sorted(source.glob('*.png')):
        original=Image.open(path).convert('RGBA');target=path.with_suffix('.webp')
        if not target.exists(): original.save(target,'WEBP',lossless=True,exact=True,method=6)
        encoded=Image.open(target).convert('RGBA')
        if original.size!=encoded.size or original.tobytes()!=encoded.tobytes():raise ValueError('RGBA differs: '+path.name)
        records.append({'asset':str(target.relative_to(ROOT)),'original_bytes':path.stat().st_size,'encoded_bytes':target.stat().st_size,'rgba_identical':True})
        backup=archive/path.name
        if backup.exists():raise ValueError('original already archived: '+path.name)
        path.rename(backup)
    (ROOT/'assets-source/v2/encoding.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'images':len(records),'before_bytes':sum(r['original_bytes'] for r in records),'after_bytes':sum(r['encoded_bytes'] for r in records),'rgba_identical':True}))
if __name__=='__main__':main()
