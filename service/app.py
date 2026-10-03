import hashlib
import hmac
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from service.models import CreateRequest, SubmitRequest, SessionRequest, StoryRecord, JobTicket, JobStatus, SessionToken, BookSummary
from service.storage import Store, Conflict
from service.provider import create_provider
from service.mock import MockProvider
from service.pipeline import Pipeline

def create_app(database=None, provider=None, start_worker=True, guardian_code=None, fault=None):
    store = Store(database or os.environ.get('XCMQY_DATABASE', 'service-data/storybooks.sqlite'))
    if provider is None:
        provider = MockProvider() if os.environ.get('XCMQY_DEVELOPMENT_MOCK') == '1' else create_provider()
    code = guardian_code or os.environ.get('XCMQY_GUARDIAN_CODE', '')
    if len(code) < 8:
        raise ValueError('XCMQY_GUARDIAN_CODE must contain at least 8 characters')
    pipeline = Pipeline(store, provider, fault)
    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            pipeline.start()
        yield
        pipeline.close()
    app = FastAPI(title='熊出没奇遇互动绘本', version='2.0.0-alpha.1', lifespan=lifespan)
    app.state.store, app.state.pipeline = store, pipeline
    security = HTTPBearer(auto_error=False)
    def account(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
        if not credentials:
            raise HTTPException(401, 'session required')
        digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        with store.db() as db:
            row = db.execute('SELECT account FROM tokens WHERE hash=? AND expires>?', (digest, time.time())).fetchone()
        if not row:
            raise HTTPException(401, 'session expired')
        return row[0]
    def translate(fn, *args):
        try:
            return fn(*args)
        except KeyError:
            raise HTTPException(404, 'resource not found')
        except Conflict as exc:
            raise HTTPException(409, str(exc))
    @app.get('/health')
    def health():
        return {'version': 2, 'mock': provider.is_mock, 'assets': len(pipeline.manifest)}
    @app.post('/v2/sessions', response_model=SessionToken)
    def session(body: SessionRequest):
        if not hmac.compare_digest(body.guardian_code, code):
            raise HTTPException(403, 'guardian code invalid')
        secret_hash = hashlib.sha256(body.account_secret.encode()).hexdigest()
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT secret FROM accounts WHERE id=?', (body.account_id,)).fetchone()
            if old and not hmac.compare_digest(old[0], secret_hash):
                raise HTTPException(403, 'account credentials invalid')
            db.execute('INSERT OR IGNORE INTO accounts VALUES(?,?)', (body.account_id, secret_hash))
            token = secrets.token_urlsafe(32)
            expires = time.time() + 3600
            db.execute('DELETE FROM tokens WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO tokens VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), body.account_id, expires))
        return {'access_token': token, 'expires_at': expires, 'mock': provider.is_mock}
    @app.post('/v2/stories', status_code=202, response_model=JobTicket)
    def create(body: CreateRequest, aid=Depends(account)):
        if body.settings.character not in {'光头强','熊大','熊二','吉吉国王','毛毛','赵琳','天才威','大马猴','二狗'}:
            raise HTTPException(422, 'unknown character')
        if not set(body.settings.assets) <= set(pipeline.manifest):
            raise HTTPException(422, 'unknown assets')
        jid = translate(store.enqueue, aid, 'create', body.model_dump())
        pipeline.wake.set()
        return {'job_id': jid}
    @app.post('/v2/stories/{sid}/actions', status_code=202, response_model=JobTicket)
    def submit(sid: str, body: SubmitRequest, aid=Depends(account)):
        if not body.operations and not body.text.strip() and not body.clarification_job:
            raise HTTPException(422, 'action or free text required')
        jid = translate(store.enqueue, aid, 'turn', body.model_dump(), sid)
        pipeline.wake.set()
        return {'job_id': jid}
    @app.get('/v2/jobs/{jid}', response_model=JobStatus)
    def job(jid: str, aid=Depends(account)):
        j = translate(store.job, jid, aid)
        return {k: j[k] for k in ['id', 'story', 'phase', 'result', 'error', 'metrics']}
    @app.post('/v2/jobs/{jid}/retry', status_code=202, response_model=JobTicket)
    def retry(jid: str, aid=Depends(account)):
        translate(store.retry, jid, aid)
        pipeline.wake.set()
        return {'job_id': jid}
    @app.get('/v2/stories/{sid}', response_model=StoryRecord)
    def restore(sid: str, aid=Depends(account)):
        result = translate(store.story, sid, aid)
        with store.db() as db:
            row = db.execute("SELECT id,request,phase FROM jobs WHERE story=? AND account=? AND phase!='complete' AND json_extract(request,'$.version')=? ORDER BY created DESC LIMIT 1", (sid, aid,result['state']['version'])).fetchone()
        result['pending'] = {'job_id': row[0], 'request': __import__('json').loads(row[1]), 'phase': row[2]} if row else None
        return result
    @app.get('/v2/books', response_model=list[BookSummary])
    def books(aid=Depends(account)):
        return [{'id': s['id'], 'title': s['blueprint']['title'], 'status': s['status'], 'pages': len(s['pages']), 'mock': s['mock']} for s in store.books(aid)]
    @app.get('/v2/books/{sid}', response_model=StoryRecord)
    def book(sid: str, aid=Depends(account)):
        return translate(store.story, sid, aid)
    @app.delete('/v2/books/{sid}', status_code=204)
    def delete(sid: str, aid=Depends(account)):
        translate(store.delete, sid, aid)
    return app
