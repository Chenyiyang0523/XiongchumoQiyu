"""Network plumbing shared by the chat, image and TTS clients.

Ren'Py 8.5's bundled Python 3.12 is built with an OPENSSLDIR that does not exist on
players' machines, so the default SSL context has no CA certificates and every HTTPS
call fails with CERTIFICATE_VERIFY_FAILED. Ren'Py ships certifi; use its bundle.
"""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request

_CTX: ssl.SSLContext | None = None


def make_ssl_context() -> ssl.SSLContext:
    global _CTX
    if _CTX is None:
        try:
            import certifi  # bundled with Ren'Py; optional elsewhere
            _CTX = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            _CTX = ssl.create_default_context()
    return _CTX


def build_opener(use_system_proxy: bool = False) -> urllib.request.OpenerDirector:
    handlers: list = [urllib.request.HTTPSHandler(context=make_ssl_context())]
    if not use_system_proxy:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def is_tls_error(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", None)
    return isinstance(exc, ssl.SSLError) or isinstance(reason, ssl.SSLError)
