"""Stdlib-only desktop transport and atomic account-isolated book files."""
import json
import os
import re
import uuid
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse
from urllib.error import HTTPError

class ClientError(ValueError):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClientError('服务地址发生跳转，请监护人配置最终的服务地址。')

def secure_endpoint(endpoint):
    parsed = urlparse(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ClientError('服务地址不能包含凭据、查询参数或片段。')
    if not parsed.hostname or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'})):
        raise ClientError('请使用 HTTPS 服务地址；本机开发可使用 localhost。')
    return endpoint.rstrip('/')

class Client:
    def __init__(self, endpoint, token=''):
        self.endpoint = secure_endpoint(endpoint)
        self.token = token

    def request(self, route, data=None, method=None):
        raw = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        try:
            with build_opener(NoRedirect).open(Request(self.endpoint + route, data=raw, headers=headers, method=method or ('POST' if raw else 'GET')), timeout=20) as response:
                content = response.read(5 * 1024 * 1024 + 1)
                if len(content) > 5 * 1024 * 1024:
                    raise ClientError('服务响应过大，已保留当前页面。')
                return json.loads(content) if content else None
        except HTTPError as exc:
            if exc.code == 401:
                raise ClientError('访问会话已过期，请监护人重新连接；当前绘本已保留。')
            if exc.code == 409:
                raise ClientError('故事已有更新或待处理行动，请恢复当前绘本。')
            if exc.code == 403:
                raise ClientError('监护人访问码或账户凭据不正确。')
            raise ClientError('服务暂时无法完成请求（%s），可以重试。' % exc.code) from exc
        except (OSError, ValueError) as exc:
            if isinstance(exc, ClientError):
                raise
            raise ClientError('暂时无法连接服务。已有页面可以继续阅读；恢复联网后可重试。') from exc

class Library:
    def __init__(self, base, account_id):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{16,80}', account_id):
            raise ClientError('无效的绘本账户。')
        self.path = Path(base) / 'books_v2' / account_id
        self.path.mkdir(parents=True, exist_ok=True)

    def filename(self, sid):
        if not re.fullmatch(r'[a-f0-9]{32}', sid):
            raise ClientError('无效的绘本编号。')
        return self.path / (sid + '.json')

    def save(self, record):
        target = self.filename(record['id'])
        temporary = target.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as output:
            json.dump(record, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)

    def load(self, sid):
        with self.filename(sid).open(encoding='utf-8') as source:
            result = json.load(source)
        if result.get('schema_version') != 2:
            raise ClientError('绘本版本不兼容，原文件已保留。')
        return result

    def list(self):
        result = []
        for path in self.path.glob('*.json'):
            try:
                book = self.load(path.stem)
                result.append(book)
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda b: b.get('saved_at', 0), reverse=True)

def new_key():
    return uuid.uuid4().hex
