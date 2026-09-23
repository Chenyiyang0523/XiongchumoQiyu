#!/usr/bin/env python3
"""Verify resources in our own freshly built ZIP/RPA archives (not untrusted inputs)."""
import hashlib
import io
import json
import pickle
import sys
import zipfile
import zlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
expected = {str(p.relative_to(root / 'game')): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root / 'game').rglob('*') if p.is_file() and p.suffix in ('.mp3', '.ogg', '.ttf', '.webp', '.png', '.jpg')}

def read_rpa(raw):
    stream = io.BytesIO(raw)
    version, offset, key = stream.readline().split()
    assert version == b'RPA-3.0', version
    stream.seek(int(offset, 16))
    index = pickle.loads(zlib.decompress(stream.read()))
    result = {}
    for name, chunks in index.items():
        content = b''
        for item in chunks:
            pos, size = item[0] ^ int(key, 16), item[1] ^ int(key, 16)
            prefix = item[2] if len(item) > 2 else b''
            if isinstance(prefix, str): prefix = prefix.encode('latin1')
            content += prefix + raw[pos:pos + size - len(prefix)]
        result[name.decode() if isinstance(name, bytes) else name] = content
    return result

summaries = []
for arg in sys.argv[1:]:
    path = Path(arg)
    resources = {}
    with zipfile.ZipFile(path) as package:
        for name in package.namelist():
            if name.endswith('/') or '/game/' not in name: continue
            rel = name.split('/game/', 1)[1]
            data = package.read(name)
            if rel.endswith('.rpa'): resources.update(read_rpa(data))
            else: resources[rel] = data
    for name, digest in expected.items():
        assert name in resources, f'{path.name}: missing {name}'
        assert hashlib.sha256(resources[name]).hexdigest() == digest, f'{path.name}: changed {name}'
    for script in (root / 'game').glob('*.rpy'):
        assert script.name + 'c' in resources, f'missing {script.name}c'
    assert not any(name.endswith('.rpy') for name in resources), 'source leaked'
    forbidden = ('saves/', 'tts_cache/', 'python-packages/', 'qa_visual', 'qa_regression')
    assert not any(token in name for name in resources for token in forbidden), 'test/runtime content leaked'
    summaries.append({'package': path.name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'resources_verified_by_hash': len(expected), 'game_entries': len(resources), 'music_present': 'audio/music.mp3' in resources})
print(json.dumps(summaries, ensure_ascii=False, indent=2))
