#!/usr/bin/env python3
"""Fetch immutable CI evidence without forwarding GitHub credentials to blobs."""
import argparse,json,subprocess,sys,time,zipfile,hashlib
from pathlib import Path
from urllib.parse import urlparse
import httpx

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=int);p.add_argument('--output',required=True,type=Path);p.add_argument('--proxy');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    token=subprocess.check_output(['gh','auth','token'],text=True).strip()
    base='https://api.github.com/repos/Chenyiyang0523/XiongchumoQiyu'
    with httpx.Client(timeout=30,http2=False,proxy=a.proxy,headers={'Authorization':'Bearer '+token}) as api:
        run=api.get(base+'/actions/runs/'+str(a.run));run.raise_for_status();expected_commit=run.json()['head_sha']
        r=api.get(base+'/actions/runs/'+str(a.run)+'/artifacts');r.raise_for_status()
        artifacts=[x for x in r.json()['artifacts'] if x['name'].startswith('picturebook-')]
        for artifact in artifacts:
            name=artifact['name'];dest=a.output/name;dest.mkdir(exist_ok=True)
            if (dest/'platform.json').exists():
                old=json.loads((dest/'platform.json').read_text())
                package=dest/'packages'/old['package']
                if old.get('verified') is True and old['source_commit']==expected_commit and package.exists() and hashlib.sha256(package.read_bytes()).hexdigest()==old['package_sha256']:
                    print(name,'already retained',flush=True);continue
            archive=a.output/(name+'.zip')
            metadata=a.output/(name+'.download.json')
            identity={'run':a.run,'artifact':artifact['id']}
            if not metadata.exists() or json.loads(metadata.read_text())!=identity:
                archive.unlink(missing_ok=True);metadata.write_text(json.dumps(identity))
            for attempt in range(8):
                try:
                    response=api.get(base+'/actions/artifacts/'+str(artifact['id'])+'/zip')
                    location=response.headers.get('location')
                    if response.status_code not in {301,302,307,308} or not location or urlparse(location).scheme!='https':
                        raise ValueError('artifact redirect unavailable')
                    # The signed storage request has no GitHub authorization header.
                    with httpx.Client(timeout=httpx.Timeout(30,read=45),http2=False,proxy=a.proxy) as blob:
                        offset=archive.stat().st_size if archive.exists() else 0
                        with blob.stream('GET',location,headers={'Range':'bytes='+str(offset)+'-'} if offset else {}) as download:
                            if download.status_code not in {200,206}:raise ValueError('artifact HTTP '+str(download.status_code))
                            if download.status_code==206 and not download.headers.get('content-range','').startswith('bytes '+str(offset)+'-'):
                                raise ValueError('unexpected artifact range')
                            append=download.status_code==206
                            total=offset if append else 0;last=time.monotonic()
                            with archive.open('ab' if append else 'wb') as output:
                                for block in download.iter_bytes(1024*1024):
                                    output.write(block);total+=len(block)
                                    if time.monotonic()-last>10:
                                        print(name,total//1024//1024,'MiB',flush=True);last=time.monotonic()
                    with zipfile.ZipFile(archive) as z:
                        if z.testzip():raise ValueError('artifact checksum failed')
                        for entry in z.infolist():
                            if not (dest/entry.filename).resolve().is_relative_to(dest.resolve()):raise ValueError('unsafe artifact path')
                        z.extractall(dest)
                    receipt=json.loads((dest/'platform.json').read_text(encoding='utf-8'))
                    package=dest/'packages'/receipt['package']
                    if receipt['source_commit']!=expected_commit or hashlib.sha256(package.read_bytes()).hexdigest()!=receipt['package_sha256']:
                        raise ValueError('artifact source or package checksum mismatch')
                    print(name,'verified='+str(receipt['verified']),receipt.get('assertions_passed'),flush=True)
                    break
                except (httpx.HTTPError,ValueError,zipfile.BadZipFile):
                    print(name,'download failed, attempt',attempt+1,flush=True)
                    if attempt==7:return 1
                    time.sleep(2)
            archive.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
    return 0
if __name__=='__main__':sys.exit(main())
