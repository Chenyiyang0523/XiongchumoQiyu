"""Bound GLM calls across local evaluation processes; OS locks survive crashes."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import time


@contextmanager
def request_slot(endpoint, count=2, timeout=600, directory=None):
    root=Path(directory or (Path(tempfile.gettempdir())/('xcmqy-glm-slots-'+str(os.getuid() if hasattr(os,'getuid') else 'local'))))
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    group=hashlib.sha256(endpoint.encode()).hexdigest()[:20]
    started=time.monotonic();held=None
    try:
        while held is None:
            for index in range(count):
                handle=os.fdopen(os.open(root/(group+'-'+str(index)+'.lock'),os.O_CREAT|os.O_RDWR,0o600),'r+b',buffering=0)
                if os.fstat(handle.fileno()).st_size==0:handle.write(b'0')
                handle.seek(0)
                try:
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    held=handle;break
                except OSError as exc:
                    handle.close()
                    if exc.errno not in {11,13,35,36}:raise
            if held is None:
                if time.monotonic()-started>=timeout:raise TimeoutError('local GLM admission queue timed out')
                time.sleep(.05)
        yield round(time.monotonic()-started,3)
    finally:
        if held is not None:held.close()
