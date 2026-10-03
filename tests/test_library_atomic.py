import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from storybook.client import Library

SID='a'*32


def test_transient_windows_replacement_denial_preserves_atomic_checkpoint(tmp_path,monkeypatch):
    lib=Library(tmp_path,'account_atomic_001');old={'id':SID,'schema_version':2,'version':1};lib.save(old)
    import storybook.client as client
    real_replace=client.os.replace;attempts=[]
    def replace(source,target):
        attempts.append(source)
        if len(attempts)<3:
            assert json.loads(target.read_text())==old
            raise PermissionError('file temporarily held')
        real_replace(source,target)
    monkeypatch.setattr(client.os,'replace',replace);monkeypatch.setattr(client.time,'sleep',lambda _:None)
    lib.save({**old,'version':2})
    assert lib.load(SID)['version']==2 and len(attempts)==3 and not list(lib.path.glob('*.tmp'))


def test_permanent_write_denial_keeps_old_checkpoint_and_cleans_temp(tmp_path,monkeypatch):
    lib=Library(tmp_path,'account_atomic_002');old={'id':SID,'schema_version':2,'version':1};lib.save(old)
    import storybook.client as client
    monkeypatch.setattr(client.os,'replace',lambda *_: (_ for _ in ()).throw(PermissionError()))
    monkeypatch.setattr(client.time,'sleep',lambda _:None)
    with pytest.raises(PermissionError):lib.save({**old,'version':2})
    assert lib.load(SID)==old and not list(lib.path.glob('*.tmp'))


def test_independent_library_instances_serialize_readers_and_writers(tmp_path):
    writer=Library(tmp_path,'account_atomic_003');reader=Library(tmp_path,'account_atomic_003')
    writer.save({'id':SID,'schema_version':2,'version':0,'data':'中文'*100})
    def write():
        for i in range(100):writer.save({'id':SID,'schema_version':2,'version':i+1,'data':'中文'*100})
    def read():
        for _ in range(200):
            record=reader.load(SID)
            assert record['data']=='中文'*100 and 0<=record['version']<=100
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(write),pool.submit(read),pool.submit(read)]
        for f in futures:f.result()
    assert reader.load(SID)['version']==100
