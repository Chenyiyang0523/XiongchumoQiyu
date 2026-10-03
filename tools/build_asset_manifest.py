#!/usr/bin/env python3
"""Only existing, usable files may enter the runtime capability list."""
import json
import hashlib
from PIL import Image
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = {'xiongda': '熊大', 'xionger': '熊二', 'guangtouqiang': '光头强', 'jijiguowang': '吉吉国王',
              'maomao': '毛毛', 'zhaolin': '赵琳', 'tiancaiwei': '天才威', 'damahou': '大马猴', 'ergou': '二狗'}
SCENES = ['forest', 'cabin', 'cave', 'riverside', 'mountain', 'village', 'bamboo', 'lakeside', 'bridge',
          'flowers', 'orchard', 'treehouse', 'camp', 'workshop', 'library', 'market', 'stage', 'sports']
EMOTIONS = ['calm', 'happy', 'thinking', 'surprised', 'worried', 'determined']
PROPS = ['map', 'feather', 'footprint', 'letter', 'bell', 'ribbon', 'key', 'compass', 'magnifier', 'rope',
         'hammer', 'scissors', 'lantern', 'bucket', 'brush', 'shovel', 'plank', 'bamboo', 'cloth', 'paper',
         'clay', 'string', 'paint', 'wheel', 'leaf', 'flower', 'pinecone', 'apple', 'honey', 'seed',
         'kite', 'drum', 'flag', 'basket', 'mask', 'star']
def find(name):
    for ext in [".webp", ".png"]:
        p=ROOT / "game/images/v2" / (name+ext)
        if p.exists(): return p
    return None

def build():
    assets = {}
    for name in SCENES:
        old = ROOT / 'game' / 'images' / 'bg' / ('bg_' + name + '.webp')
        new = find('scene_'+name+'_approved') or find('scene_'+name)
        path = new or old
        if path.exists():
            assets['scene.' + name] = {'kind': 'scene', 'path': str(path.relative_to(ROOT / 'game')), 'regions': ['left', 'center', 'right', 'ground']}
    for cid, name in CHARACTERS.items():
        for emotion in EMOTIONS:
            old = ROOT / 'game/images/sprites' / (cid + '_normal.png')
            new = find(cid+'_'+emotion+'_clean') or find(cid+'_'+emotion)
            path = new or (old if emotion == 'calm' else None)
            if path and path.exists():
                assets['character.' + cid + '.' + emotion] = {'kind': 'character', 'character': name, 'emotion': emotion,
                     'path': str(path.relative_to(ROOT / 'game')), 'scale': {'maomao':.45,'jijiguowang':.72,'zhaolin':.90,'guangtouqiang':.9,'ergou':.85,'tiancaiwei':.92}.get(cid,1), 'regions': ['left', 'center', 'right']}
    for prop in PROPS:
        path = find('prop_'+prop+'_approved') or find('prop_'+prop)
        if path:
            assets['prop.' + prop] = {'kind': 'prop', 'path': str(path.relative_to(ROOT / 'game')), 'regions': ['ground'], 'hotspot': True}
    for i in range(12):
        path = find('key_%02d' % i)
        spec_path = ROOT / 'assets-source/v2' / ('key_%02d.json' % i)
        if path and spec_path.exists():
            spec = json.loads(spec_path.read_text())
            assets['key.%02d' % i] = {'kind': 'key_art', 'path': str(path.relative_to(ROOT / 'game')), **spec}
    for aid,spec in assets.items():
        path=ROOT/'game'/spec['path']
        image=Image.open(path).convert('RGBA')
        spec.update(width=image.width,height=image.height,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
        if spec['kind'] in {'character','prop'}:
            alpha=image.getchannel('A')
            lo,hi=alpha.getextrema()
            if lo!=0 or hi<240 or alpha.histogram()[0] < image.width*image.height*.10: raise ValueError('not a transparent cutout: '+aid)
            spec['alpha_range']=[lo,hi]
            spec['alpha']=True
    target = ROOT / 'game/storybook/asset_manifest.json'
    target.write_text(json.dumps({'schema_version': 2, 'assets': assets}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: sum(a['kind'] == k for a in assets.values()) for k in ['scene', 'character', 'prop', 'key_art']}))
    return assets
if __name__ == '__main__':
    build()
