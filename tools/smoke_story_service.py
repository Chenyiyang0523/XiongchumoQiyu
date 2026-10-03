#!/usr/bin/env python3
"""Exercise the deployed HTTP service and its idempotency boundary."""
import argparse,json,secrets,time,subprocess,sys,os
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'game')]
from tools.evaluate_books import choose_operations,checks,measured_usage
def main():
    p=argparse.ArgumentParser();p.add_argument('--endpoint',default='http://127.0.0.1:8001');p.add_argument('--guardian',default='local-dev-guardian');p.add_argument('--guardian-file',type=Path);p.add_argument('--mode',choices=['live','mock'],default='mock');p.add_argument('--job-timeout',type=int,default=900);p.add_argument('--output',type=Path,default=Path('docs/v2/container-smoke.json'));p.add_argument('--restart-container',help='Restart this explicitly selected QA container and verify durable restore');p.add_argument('--checkpoint',type=Path,default=ROOT/'.local/glm/http-smoke-private.json');p.add_argument('--retry-failed',action='store_true');p.add_argument('--attempts',type=int,choices=[1,2,3],default=1);a=p.parse_args()
    guardian=a.guardian_file.read_text(encoding='utf-8').strip() if a.guardian_file else a.guardian
    assets=list(json.loads((ROOT/'game/storybook/asset_manifest.json').read_text(encoding='utf-8'))['assets'])
    saved=json.loads(a.checkpoint.read_text(encoding='utf-8')) if a.checkpoint.exists() else {
        'endpoint':a.endpoint,'mode':a.mode,'account_id':secrets.token_hex(16),'account_secret':secrets.token_hex(32),
        'create':{'settings':{'theme':'森林音乐会','character':'熊大','age':'6-8','pages':8,'assets':assets},'idempotency_key':secrets.token_hex(16)}}
    assert saved['endpoint']==a.endpoint and saved['mode']==a.mode
    def checkpoint():
        a.checkpoint.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(a.checkpoint,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(saved,f,ensure_ascii=False)
        a.checkpoint.chmod(0o600)
    checkpoint()
    with httpx.Client(base_url=a.endpoint,timeout=20) as c:
        health=c.get('/health').json()
        assert health['mock']==(a.mode=='mock')
        r=c.post('/v2/sessions',json={'account_id':saved['account_id'],'account_secret':saved['account_secret'],'guardian_code':guardian,'consent':True});r.raise_for_status();c.headers['Authorization']='Bearer '+r.json()['access_token']
        payload=saved['create']
        def finish(jid):
            deadline=time.monotonic()+a.job_timeout
            retries=0
            while time.monotonic()<deadline:
                r=c.get('/v2/jobs/'+jid);r.raise_for_status();job=r.json()
                if job['phase']=='failed':
                    if a.retry_failed and retries<a.attempts-1:
                        retry=c.post('/v2/jobs/'+jid+'/retry',json={});retry.raise_for_status();retries+=1;continue
                    raise ValueError(job['error'])
                if job['phase']=='complete':return c.get('/v2/stories/'+job['result']['story_id']).json()
                time.sleep(.5)
            raise TimeoutError('job wait')
        r=c.post('/v2/stories',json=payload);r.raise_for_status();sid=r.json()['job_id'];assert c.post('/v2/stories',json=payload).json()['job_id']==sid;book=finish(sid)
        saved['story_id']=sid;checkpoint()
        restarted=saved.get('restart_verified',False)
        if a.restart_container and not restarted:
            subprocess.run(['docker','restart',a.restart_container],check=True,capture_output=True)
            for _ in range(100):
                try:
                    restored=c.get('/v2/stories/'+sid);restored.raise_for_status()
                    assert restored.json()['state']==book['state'] and restored.json()['pages']==book['pages']
                    restarted=True;break
                except httpx.HTTPError:time.sleep(.2)
            assert restarted
            saved['restart_verified']=True;checkpoint()
        while book['status']=='active':
            payload=saved.get('pending') or {'version':book['state']['version'],'idempotency_key':secrets.token_hex(16),'operations':choose_operations(book,1)}
            saved['pending']=payload;checkpoint()
            r=c.post('/v2/stories/'+sid+'/actions',json=payload);r.raise_for_status();jid=r.json()['job_id'];assert c.post('/v2/stories/'+sid+'/actions',json=payload).json()['job_id']==jid;book=finish(jid)
            saved.pop('pending',None);checkpoint()
            print('confirmed pages',len(book['pages']),'status',book['status'],flush=True)
        result=checks(book);assert result['completed'] and book['mock']==(a.mode=='mock')
        result.update(measured_usage(book['usage']))
        result.update(health=health,story_id=sid,version=book['state']['version'],pages=len(book['pages']),events=len(book['events']),
                      ending=book['ending']['title'],idempotency_verified=True,restart_restore_verified=restarted,mock=book['mock'],http_service=True)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.with_suffix('.book.json').write_text(json.dumps(book,ensure_ascii=False,indent=2),encoding='utf-8')
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(a.output)
if __name__=='__main__':main()
