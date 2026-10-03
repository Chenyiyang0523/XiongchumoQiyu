#!/usr/bin/env python3
"""Exercise the deployed HTTP service and its idempotency boundary."""
import argparse,json,secrets,time,subprocess,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'game')]
from tools.evaluate_books import choose_operations,checks,measured_usage
def main():
    p=argparse.ArgumentParser();p.add_argument('--endpoint',default='http://127.0.0.1:8001');p.add_argument('--guardian',default='local-dev-guardian');p.add_argument('--guardian-file',type=Path);p.add_argument('--mode',choices=['live','mock'],default='mock');p.add_argument('--job-timeout',type=int,default=900);p.add_argument('--output',type=Path,default=Path('docs/v2/container-smoke.json'));p.add_argument('--restart-container',help='Restart this explicitly selected QA container and verify durable restore');a=p.parse_args()
    guardian=a.guardian_file.read_text(encoding='utf-8').strip() if a.guardian_file else a.guardian
    with httpx.Client(base_url=a.endpoint,timeout=20) as c:
        health=c.get('/health').json()
        assert health['mock']==(a.mode=='mock')
        r=c.post('/v2/sessions',json={'account_id':secrets.token_hex(16),'account_secret':secrets.token_hex(32),'guardian_code':guardian,'consent':True});r.raise_for_status();c.headers['Authorization']='Bearer '+r.json()['access_token']
        assets=list(json.loads(Path('game/storybook/asset_manifest.json').read_text())['assets'])
        payload={'settings':{'theme':'森林音乐会','character':'熊大','age':'6-8','pages':8,'assets':assets},'idempotency_key':secrets.token_hex(16)}
        def finish(jid):
            deadline=time.monotonic()+a.job_timeout
            while time.monotonic()<deadline:
                r=c.get('/v2/jobs/'+jid);r.raise_for_status();job=r.json()
                if job['phase']=='failed':raise ValueError(job['error'])
                if job['phase']=='complete':return c.get('/v2/stories/'+job['result']['story_id']).json()
                time.sleep(.5)
            raise TimeoutError('job wait')
        r=c.post('/v2/stories',json=payload);r.raise_for_status();sid=r.json()['job_id'];assert c.post('/v2/stories',json=payload).json()['job_id']==sid;book=finish(sid)
        restarted=False
        if a.restart_container:
            subprocess.run(['docker','restart',a.restart_container],check=True,capture_output=True)
            for _ in range(100):
                try:
                    restored=c.get('/v2/stories/'+sid);restored.raise_for_status()
                    assert restored.json()['state']==book['state'] and restored.json()['pages']==book['pages']
                    restarted=True;break
                except httpx.HTTPError:time.sleep(.2)
            assert restarted
        while book['status']=='active':
            payload={'version':book['state']['version'],'idempotency_key':secrets.token_hex(16),'operations':choose_operations(book,1)}
            r=c.post('/v2/stories/'+sid+'/actions',json=payload);r.raise_for_status();jid=r.json()['job_id'];assert c.post('/v2/stories/'+sid+'/actions',json=payload).json()['job_id']==jid;book=finish(jid)
        result=checks(book);assert result['completed'] and book['mock']==(a.mode=='mock')
        result.update(measured_usage(book['usage']))
        result.update(health=health,story_id=sid,version=book['state']['version'],pages=len(book['pages']),events=len(book['events']),
                      ending=book['ending']['title'],idempotency_verified=True,restart_restore_verified=restarted,mock=book['mock'],http_service=True)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.with_suffix('.book.json').write_text(json.dumps(book,ensure_ascii=False,indent=2),encoding='utf-8')
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(a.output)
if __name__=='__main__':main()
