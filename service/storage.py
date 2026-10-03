"""SQLite transaction boundary for queue, snapshot, ledger, pages and idempotency."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

class Conflict(ValueError):
    pass

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.db() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, secret TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, account TEXT NOT NULL, expires REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS stories(id TEXT PRIMARY KEY, account TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, account TEXT NOT NULL, story TEXT, kind TEXT NOT NULL,
                ikey TEXT NOT NULL, digest TEXT NOT NULL, request TEXT NOT NULL, phase TEXT NOT NULL,
                result TEXT, error TEXT, metrics TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                UNIQUE(account, ikey));
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET phase='queued' WHERE phase IN ('planning','generating','reviewing','committing')")

    def enqueue(self, account, kind, request, story=None):
        raw = encode(request)
        digest = hashlib.sha256((kind + ':' + str(story) + ':' + raw).encode()).hexdigest()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM jobs WHERE account=? AND ikey=?', (account, request['idempotency_key'])).fetchone()
            if old:
                if old['digest'] != digest:
                    raise Conflict('idempotency key reused with different payload')
                return old['id']
            if story:
                current = db.execute('SELECT * FROM stories WHERE id=? AND account=?', (story, account)).fetchone()
                if not current:
                    raise KeyError(story)
                if current['version'] != request['version']:
                    raise Conflict('stale state version')
                if db.execute("SELECT 1 FROM jobs WHERE story=? AND phase NOT IN ('complete','failed')", (story,)).fetchone():
                    raise Conflict('story already has a pending action')
                if json.loads(current['data']).get('ending'):
                    raise Conflict('story already completed')
            jid = uuid.uuid4().hex
            now = time.time()
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (jid, account, story, kind, request['idempotency_key'], digest, raw, 'queued', None, None, '[]', now, now))
            return jid

    def next_job(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE phase='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET phase='planning',updated=? WHERE id=?", (time.time(), row['id']))
                return dict(row)

    def job(self, jid, account=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?' + (' AND account=?' if account else ''),
                             (jid, account) if account else (jid,)).fetchone()
        if not row:
            raise KeyError(jid)
        data = dict(row)
        for key in ('request', 'result', 'metrics'):
            data[key] = json.loads(data[key]) if data[key] else None
        return data

    def phase(self, jid, phase):
        with self.db() as db:
            db.execute('UPDATE jobs SET phase=?,updated=? WHERE id=?', (phase, time.time(), jid))

    def metric(self, jid, metric, index=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            metrics = json.loads(db.execute('SELECT metrics FROM jobs WHERE id=?', (jid,)).fetchone()[0])
            if index is None:
                index=len(metrics)
                metrics.append(metric)
            else:
                metrics[index]=metric
            db.execute('UPDATE jobs SET metrics=? WHERE id=?', (encode(metrics), jid))
            return index

    def usage(self, sid, creation_job=None):
        # Failed calls, clarification and retries count even if no page was committed.
        with self.db() as db:
            rows = db.execute('SELECT metrics FROM jobs WHERE story=? OR id=? ORDER BY created',
                              (sid, creation_job or sid)).fetchall()
        return [metric for row in rows for metric in json.loads(row[0])]

    def commit(self, job, story, result=None, fault=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT version FROM stories WHERE id=?', (story['id'],)).fetchone()
            if job['kind'] == 'turn':
                expected = json.loads(job['request'])['version']
                if not current or current[0] != expected:
                    raise Conflict('state changed while generating')
            db.execute('INSERT INTO stories VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data',
                       (story['id'], job['account'], story['state']['version'], encode(story)))
            if fault:
                fault('commit')
            db.execute("UPDATE jobs SET phase='complete',story=?,result=?,error=NULL,updated=? WHERE id=?",
                       (story['id'], encode(result or {'story_id': story['id'], 'version': story['state']['version']}), time.time(), job['id']))

    def complete_without_change(self, jid, result):
        with self.db() as db:
            db.execute("UPDATE jobs SET phase='complete',result=?,updated=? WHERE id=?", (encode(result), time.time(), jid))

    def fail(self, jid, message):
        with self.db() as db:
            db.execute("UPDATE jobs SET phase='failed',error=?,updated=? WHERE id=?", (message, time.time(), jid))

    def retry(self, jid, account):
        job = self.job(jid, account)
        if job['phase'] != 'failed':
            return jid
        with self.db() as db:
            if job['story']:
                current = db.execute('SELECT version FROM stories WHERE id=? AND account=?', (job['story'], account)).fetchone()
                if not current or current[0] != job['request']['version']:
                    raise Conflict('retry cannot overwrite newer facts')
                if db.execute("SELECT 1 FROM jobs WHERE story=? AND phase NOT IN ('complete','failed')", (job['story'],)).fetchone():
                    raise Conflict('story already has a pending action')
            db.execute("UPDATE jobs SET phase='queued',error=NULL,updated=? WHERE id=?", (time.time(), jid))
        return jid

    def story(self, sid, account=None):
        with self.db() as db:
            row = db.execute('SELECT data FROM stories WHERE id=?' + (' AND account=?' if account else ''),
                             (sid, account) if account else (sid,)).fetchone()
        if not row:
            raise KeyError(sid)
        return json.loads(row[0])

    def books(self, account):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM stories WHERE account=? ORDER BY rowid DESC', (account,))]

    def delete(self, sid, account):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE story=? AND account=? AND phase NOT IN ('complete','failed')", (sid, account)).fetchone():
                raise Conflict('generation still pending')
            if not db.execute('DELETE FROM stories WHERE id=? AND account=?', (sid, account)).rowcount:
                raise KeyError(sid)
            db.execute('DELETE FROM jobs WHERE story=? AND account=?', (sid, account))
