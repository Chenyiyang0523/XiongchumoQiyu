#!/usr/bin/env python3
"""Build a package, then run its own native interpreter and full UI test suite."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile

if hasattr(sys.stdout,'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'.local/ci-platform'
EVIDENCE=WORK/'evidence'
SDK_HASH='f85ac72c353cd14056ae0a9e25d8a2bd27232c0de4b59e29ead9114bd68b1fa4'


def extract(archive,destination):
    with zipfile.ZipFile(archive) as z:
        z.extractall(destination)
        if os.name!='nt':
            for info in z.infolist():
                path=destination/info.filename
                if path.is_file() and info.external_attr>>16:
                    path.chmod(info.external_attr>>16)


def run(command,name,env=None,cwd=ROOT,timeout=600):
    if sys.platform.startswith('linux'):
        command=['xvfb-run','-a','--server-args=-screen 0 1920x1080x24',*map(str,command)]
    else:command=list(map(str,command))
    with (EVIDENCE/name).open('w', encoding='utf-8') as output:
        result=subprocess.run(command,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
    if result.returncode:raise RuntimeError(name+' exited '+str(result.returncode))


def main():
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    receipt={'platform':platform.system().lower(),'environment':platform.platform(),'architecture':platform.machine(),
        'installed_package':False,'verified':False,'mock':True,'real_model':False,'human_manual_play':False,
        'source_commit':os.environ.get('GITHUB_SHA'),'evidence':'package-qa.txt'}
    service=None
    try:
        sdk_zip=WORK/'renpy-sdk.zip'
        if not sdk_zip.exists():urllib.request.urlretrieve('https://www.renpy.org/dl/8.5.2/renpy-8.5.2-sdk.zip',sdk_zip)
        if hashlib.sha256(sdk_zip.read_bytes()).hexdigest()!=SDK_HASH:raise ValueError('RenPy SDK checksum mismatch')
        extract(sdk_zip,WORK/'sdk')
        sdk=next((WORK/'sdk').glob('renpy-*-sdk'))
        if os.name=='nt':
            sdk_cmd=[sdk/'lib/py3-windows-x86_64/python.exe',sdk/'renpy.py']
        else:sdk_cmd=[sdk/'renpy.sh']
        project=WORK/'source'
        shutil.copytree(ROOT/'game',project/'game',dirs_exist_ok=True,ignore=shutil.ignore_patterns('saves','cache','*.rpyc','__pycache__'))
        packages=EVIDENCE/'packages';packages.mkdir(exist_ok=True)
        kind='mac' if sys.platform=='darwin' else 'pc'
        run([*sdk_cmd,'launcher','distribute','--destination',packages,'--package',kind,'--no-update',project],
            'build.txt',env=os.environ.copy(),cwd=sdk)
        candidates=list(packages.glob('*.zip'))
        if len(candidates)!=1:raise RuntimeError('Expected exactly one platform package')
        package=candidates[0];receipt['package_sha256']=hashlib.sha256(package.read_bytes()).hexdigest();receipt['package']=package.name
        run([sys.executable,ROOT/'tools/verify_release.py',package],'package-resources.json')
        installed=WORK/'installed';extract(package,installed)
        if sys.platform=='darwin':
            app=next(installed.glob('*.app'));root=app/'Contents/Resources/autorun'
            command=[app/'Contents/MacOS'/app.stem,root]
        else:
            root=next(p for p in installed.iterdir() if p.is_dir())
            command=[root/'XiongchumoQiyu.exe',root] if os.name=='nt' else [root/'XiongchumoQiyu.sh',root]
        receipt['installed_package']=True
        shutil.copy2(ROOT/'tools/qa_book_v2.rpy',root/'game/qa_book_v2.rpy')
        # Tests are injected only into this extracted QA copy, never into the distribution.
        log=(EVIDENCE/'service.txt').open('w', encoding='utf-8')
        service_env=os.environ.copy();service_env.update(XCMQY_DEVELOPMENT_MOCK='1',XCMQY_GUARDIAN_CODE='local-dev-guardian',XCMQY_DATABASE=str(WORK/'mock.sqlite'))
        service=subprocess.Popen([sys.executable,'-m','uvicorn','service.app:create_app','--factory','--host','127.0.0.1','--port','8000'],cwd=ROOT,env=service_env,stdout=log,stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2) as response:
                    if json.load(response)['mock'] is True:break
            except Exception:
                if service.poll() is not None:raise RuntimeError('Fixture service failed to start')
                time.sleep(.2)
        else:raise RuntimeError('Fixture service never became ready')
        qa_env=os.environ.copy();qa_env.update(XCMQY_QA_OUTPUT=str(EVIDENCE/'screenshots'),RENPY_DISABLE_SOUND='1',RENPY_SIMPLE_EXCEPTIONS='1',PYTHONIOENCODING='utf-8')
        (EVIDENCE/'screenshots').mkdir(exist_ok=True)
        fixture=WORK/'local-operations.json'
        run([sys.executable,ROOT/'tools/prepare_local_fixture.py',fixture],'local-fixture.txt')
        qa_env['XCMQY_LOCAL_OPS_BOOK']=str(fixture)
        run([*command,'--savedir',WORK/'saves','test','picturebook','--overwrite-screenshots','--report-detailed'],
            'package-qa.txt',env=qa_env,timeout=300)
        output=(EVIDENCE/'package-qa.txt').read_text(errors='replace', encoding='utf-8')
        if '[rpytest] Status: PASSED' not in output or not re.search(r'Assertions\s*:\s*14\s*\|\s*14 passed',output):
            raise RuntimeError('Native package did not report all 14 assertions passing')
        run([*command,'--savedir',WORK/'saves','test','local_operations','--overwrite-screenshots','--report-detailed'],
            'local-operations-qa.txt',env=qa_env,timeout=120)
        local_output=(EVIDENCE/'local-operations-qa.txt').read_text(encoding='utf-8',errors='replace')
        if '[rpytest] Status: PASSED' not in local_output or not re.search(r'Assertions\s*:\s*4\s*\|\s*4 passed',local_output):
            raise RuntimeError('Native local collection/crafting did not pass all 4 assertions')
        qa_env['XCMQY_REAL_QA_BOOK']=str(ROOT/'docs/v2/examples/real-glm-book.json')
        run([*command,'--savedir',WORK/'saves','test','live_book_reader','--overwrite-screenshots','--report-detailed'],
            'real-book-reader-qa.txt',env=qa_env,timeout=120)
        real_output=(EVIDENCE/'real-book-reader-qa.txt').read_text(encoding='utf-8',errors='replace')
        if '[rpytest] Status: PASSED' not in real_output or not re.search(r'Assertions\s*:\s*8\s*\|\s*8 passed',real_output):
            raise RuntimeError('Reading the real GLM book offline did not pass all 8 assertions')
        receipt.update(verified=True,assertions_passed=26,live_book_read_offline=True,
                       screenshots=len(list((EVIDENCE/'screenshots').glob('*.png'))))
    except Exception as exc:
        receipt['failure']=str(exc)
        raise
    finally:
        if service:
            service.terminate()
            try:service.wait(timeout=5)
            except subprocess.TimeoutExpired:service.kill();service.wait()
        (EVIDENCE/'platform.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
        if not receipt['verified']:
            for name in ['package-resources.json','package-qa.txt','local-operations-qa.txt','real-book-reader-qa.txt','build.txt']:
                path=EVIDENCE/name
                if path.exists():print(name+'\n'+'\n'.join(path.read_text(encoding='utf-8',errors='replace').splitlines()[-65:]))
        print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
