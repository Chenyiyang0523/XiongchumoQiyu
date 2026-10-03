#!/usr/bin/env python3
"""Exercise the deployed HTTP service and its idempotency boundary."""
import argparse,json,secrets,time,subprocess
from pathlib import Path
import httpx
def main():
    p=argparse.ArgumentParser();p.add_argument('--endpoint',default='http://127.0.0.1:8001');p.add_argument('--guardian',default='local-dev-guardian');p.add_argument('--output',type=Path,default=Path('docs/v2/container-smoke.json'));p.add_argument('--restart-container',help='Restart this explicitly selected QA container and verify durable restore');a=p.parse_args()
    with httpx.Client(base_url=a.endpoint,timeout=20) as c:
        health=c.get('/health').json()
        r=c.post('/v2/sessions',json={'account_id':secrets.token_hex(16),'account_secret':secrets.token_hex(32),'guardian_code':a.guardian,'consent':True});r.raise_for_status();c.headers['Authorization']='Bearer '+r.json()['access_token']
        assets=list(json.loads(Path('game/storybook/asset_manifest.json').read_text())['assets'])
        payload={'settings':{'theme':'森林音乐会','character':'熊大','age':'6-8','pages':8,'assets':assets},'idempotency_key':secrets.token_hex(16)}
        def finish(jid):
            for _ in range(120):
                r=c.get('/v2/jobs/'+jid);r.raise_for_status();job=r.json()
                if job['phase']=='failed':raise ValueError(job['error'])
                if job['phase']=='complete':return c.get('/v2/stories/'+job['result']['story_id']).json()
                time.sleep(.1)
            raise TimeoutError('job wait')
        r=c.post('/v2/stories',json=payload);r.raise_for_status();sid=r.json()['job_id'];assert c.post('/v2/stories',json=payload).json()['job_id']==sid;book=finish(sid)
        while not book.get('ending'):
            inter=book['pages'][-1]['interactions'][0];action=inter['actions'][0];op={'action_id':action['id'],'items':action['inputs']}
            if inter.get('order_action')==action['id']:op['order']=inter['order']
            if action['verb']=='allocate':op['amount']=-next(e['value'] for e in action['effects'] if e['op']=='resource')
            payload={'version':book['state']['version'],'idempotency_key':secrets.token_hex(16),'operations':[op]}
            r=c.post('/v2/stories/'+sid+'/actions',json=payload);r.raise_for_status();jid=r.json()['job_id'];assert c.post('/v2/stories/'+sid+'/actions',json=payload).json()['job_id']==jid;book=finish(jid)
        assert book['state']['version']==9 and len(book['events'])==8 and len(book['pages'])==8
        restarted=False
        if a.restart_container:
            subprocess.run(['docker','restart',a.restart_container],check=True,capture_output=True)
            for _ in range(100):
                try:
                    restored=c.get('/v2/stories/'+sid);restored.raise_for_status()
                    assert restored.json()==book
                    restarted=True;break
                except httpx.HTTPError:time.sleep(.1)
            assert restarted
        a.output.write_text(json.dumps({'health':health,'story_id':sid,'version':9,'pages':8,'events':8,'ending':book['ending']['title'],'idempotency_verified':True,'restart_restore_verified':restarted,'mock':book['mock']},ensure_ascii=False,indent=2)+'\n')
        print(a.output)
if __name__=='__main__':main()
