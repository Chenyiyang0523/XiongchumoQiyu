"""Streaming chat client for BigModel's OpenAI-compatible endpoint (stdlib only).

Retryable failures are retried only while no content has been streamed; after
partial content an LLMError(partial=...) is raised so the caller can resume.
Errors are classified by business code first, then HTTP status.
Every attempt the server answered (HTTP 200) is billed, even when it fails: complete(meter=...) reports each one.
"""
from __future__ import annotations

import http.client
import json
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .config import Settings, resolve_api_key
from .net import build_opener, is_tls_error
from .sse import iter_sse_data, parse_chunk

RATE_CODES = {"1302", "1303", "1304"}
SERVER_CODES = {"1305", "1200", "1230", "1231", "1234"}
AUTH_CODES = {"1000", "1001", "1002", "1003", "1004", "1005",
              "1220"}           # 1220: no permission for this model, an account problem the adult must look at
BILLING_CODES = {"1112", "1113"}
QUOTA_CODES = {str(c) for c in range(1308, 1322)}       # account usage limits: never retried, callers treat as billing
SENSITIVE_CODES = {"1301"}
PROMPT_TOKENS_PER_CHAR = 0.8    # usage estimate when a stream ends without its usage chunk

# A broken connection as urllib/http.client report it, before the response arrives and while its body is read. The
# connect phase and the read phase must agree on this list: HTTPException is no OSError, yet it is what a broken proxy
# (BadStatusLine) and a chunked body cut inside a chunk (IncompleteRead, LineTooLong) raise.
_NETWORK_ERRORS = (urllib.error.URLError, ConnectionError, OSError, http.client.HTTPException)


class LLMError(Exception):
    def __init__(self, kind: str, message: str, status: int | None = None, code: str | None = None,
                 retryable: bool = False, partial: str = ""):
        super().__init__(f"{kind}: {message}")
        self.kind, self.message, self.status, self.code = kind, message, status, code
        self.retryable, self.partial = retryable, partial


class HTTPStatusError(Exception):
    def __init__(self, status: int, body: bytes):
        super().__init__(f"HTTP {status}")
        self.status, self.body = status, body


class CancelToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


@dataclass
class _Attempt:
    """What one request has received so far; read for metering also when the attempt fails."""
    answered: bool = False                  # the server answered with HTTP 200
    parts: list[str] = field(default_factory=list)
    reasoning: int = 0
    usage: dict = field(default_factory=dict)


@dataclass
class ChatResult:
    text: str
    finish_reason: str
    usage: dict
    ttft: float | None
    total: float
    model: str
    attempts: int
    reasoning_chars: int = 0


class Response(Protocol):
    status: int
    def readline(self) -> bytes: ...
    def read(self) -> bytes: ...
    def close(self) -> None: ...


class Transport(Protocol):
    def post(self, url: str, headers: dict, body: bytes, timeout: float) -> Response: ...


class UrllibTransport:
    def __init__(self, use_system_proxy: bool = False):
        self._opener = build_opener(use_system_proxy)

    def post(self, url, headers, body, timeout):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            return self._opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            raise HTTPStatusError(e.code, e.read()) from None


class _FakeResponse:
    def __init__(self, text: str, drop_after: int | None = None, clock_step: float = 0.0, advance=None,
                 drop_exc: BaseException | None = None):
        self.status = 200
        self._lines = [l + b"\n" for l in text.encode("utf-8").split(b"\n")]
        self._drop_after, self._data_seen = drop_after, 0
        self._drop_exc = drop_exc if drop_exc is not None else ConnectionResetError("dropped")
        self._clock_step, self._advance = clock_step, advance

    def readline(self) -> bytes:
        if not self._lines:
            return b""
        line = self._lines.pop(0)
        if self._clock_step and self._advance:
            self._advance(self._clock_step)
        if line.startswith(b"data:"):
            self._data_seen += 1
            if self._drop_after is not None and self._data_seen > self._drop_after:
                raise self._drop_exc
        return line

    def read(self) -> bytes:
        rest = b"".join(self._lines)
        self._lines = []
        return rest

    def close(self) -> None:
        pass


class FakeTransport:
    """Scripted transport for tests. Steps: ("ok", sse) | ("ok_then_drop", sse, n_data[, exception]) |
    ("slow", sse, seconds_per_line) | ("http", status, body) | ("exc", exception) | ("bytes", status, raw_bytes).
    ok_then_drop serves n_data data lines, then raises the exception (default ConnectionResetError) from readline()."""

    def __init__(self, script: list):
        self.script = list(script)
        self.requests: list[dict] = []
        self.advance = None

    def post(self, url, headers, body, timeout):
        self.requests.append({"url": url, "headers": dict(headers), "body": body, "timeout": timeout})
        if not self.script:
            raise AssertionError("FakeTransport script exhausted")
        step = self.script.pop(0)
        kind = step[0]
        if kind == "ok":
            return _FakeResponse(step[1])
        if kind == "ok_then_drop":
            return _FakeResponse(step[1], drop_after=step[2], drop_exc=step[3] if len(step) > 3 else None)
        if kind == "slow":
            return _FakeResponse(step[1], clock_step=step[2], advance=self.advance)
        if kind == "http":
            raise HTTPStatusError(step[1], step[2].encode("utf-8"))
        if kind == "exc":
            raise step[1]
        if kind == "bytes":
            r = _FakeResponse("")
            r.status, r._lines = step[1], [step[2]]
            return r
        raise AssertionError(f"unknown script step {kind}")


def classify_http(status: int, body: bytes) -> LLMError:
    code, message = None, body.decode("utf-8", "replace")[:300]
    try:
        err = json.loads(body).get("error") or {}
        code = str(err.get("code", "")) or None
        message = str(err.get("message", message))[:300]
    except (ValueError, AttributeError):
        pass
    if code in BILLING_CODES:
        return LLMError("billing", message, status, code)
    if code in QUOTA_CODES:
        return LLMError("quota", message, status, code)
    if code in AUTH_CODES or status in (401, 403):
        return LLMError("auth", message, status, code)
    if code in SENSITIVE_CODES:
        return LLMError("sensitive", message, status, code)
    if code in RATE_CODES or status == 429:
        return LLMError("rate", message, status, code, retryable=True)
    if code in SERVER_CODES or status >= 500:
        return LLMError("server", message, status, code, retryable=True)
    return LLMError("bad_request", message, status, code)


class ChatClient:
    def __init__(self, settings: Settings, transport: Transport | None = None, api_key: str | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[dict], None] | None = None):
        self.settings = settings
        self.transport = transport or UrllibTransport(bool(settings.get("use_system_proxy")))
        self._key = api_key if api_key is not None else resolve_api_key()
        self.clock, self.sleep, self.log = clock, sleep, log
        if isinstance(self.transport, FakeTransport):
            self.transport.advance = lambda s: self.sleep(s)

    def request_body(self, role: str, messages: list[dict], model: str | None = None,
                     temperature: float | None = None, max_tokens: int | None = None) -> dict:
        rc = self.settings.role(role)
        model = model or rc.model
        if model != rc.model:
            thinking = (self.settings.get("thinking", {}) or {}).get(model, "low")
            if role == "judge" and thinking != "disabled":
                thinking = self.settings.get("judge_thinking", "high")
        else:
            thinking = rc.thinking
        body = {"model": model, "messages": messages, "stream": True,
                "temperature": rc.temperature if temperature is None else temperature,
                "top_p": rc.top_p, "max_tokens": max_tokens or rc.max_tokens}
        if thinking == "disabled":
            body["thinking"] = {"type": "disabled"}
        else:
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = thinking
        return body

    def complete(self, role: str, messages: list[dict], *, on_text: Callable[[str], None] | None = None,
                 cancel: CancelToken | None = None, model: str | None = None,
                 temperature: float | None = None, max_tokens: int | None = None,
                 meter: Callable[[str, dict, bool], None] | None = None) -> ChatResult:
        """meter(model, usage, estimated) is called once for every attempt that got an HTTP 200 (also a failed,
        dropped or cancelled one): with the usage the stream reported, else an estimate and estimated=True."""
        if not self._key:
            raise LLMError("auth", "no API key configured")
        body = self.request_body(role, messages, model, temperature, max_tokens)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Authorization": "Bearer " + self._key, "Content-Type": "application/json",
                   "Accept": "text/event-stream"}
        url = self.settings.api_base + "/chat/completions"
        timeouts = self.settings.get("timeouts")
        total_limit = timeouts["total_bible"] if role == "bible" else timeouts["total"]
        retries = int(self.settings.get("retries"))
        request_chars = sum(len(m["content"]) for m in messages
                            if isinstance(m, dict) and isinstance(m.get("content"), str))
        attempt, start = 0, self.clock()
        while True:
            attempt += 1
            seen = _Attempt()
            try:
                res = self._once(url, headers, payload, body["model"], timeouts["idle"], total_limit,
                                 start, on_text, cancel, attempt, seen)
                self._log(role, body["model"], res, None)
                return res
            except LLMError as e:
                # The total budget covers all attempts together: once it is spent another attempt could only trip
                # the same deadline at its first streamed line (and still be billed), so the error is raised as is.
                budget_left = self.clock() - start <= total_limit
                if (e.retryable and not e.partial and attempt <= retries and budget_left
                        and not (cancel and cancel.cancelled)):
                    self.sleep(min(20.0, (2 ** (attempt - 1)) * 1.5 + random.uniform(0, 0.5)))
                    continue
                self._log(role, body["model"], None, e, attempt)
                raise
            finally:
                if meter is not None and seen.answered:
                    self._meter(meter, body["model"], seen, request_chars)

    def _once(self, url, headers, payload, model, idle, total_limit, start, on_text, cancel, attempt, seen: _Attempt):
        text_parts = seen.parts
        ttft, finish = None, None
        t0 = self.clock()
        try:
            resp = self.transport.post(url, headers, payload, timeout=idle)
        except HTTPStatusError as e:
            raise classify_http(e.status, e.body) from None
        except (socket.timeout, TimeoutError):
            raise LLMError("timeout", "connect/first byte timeout", retryable=True) from None
        except _NETWORK_ERRORS as e:
            if is_tls_error(e):
                raise LLMError("tls", "TLS/certificate failure: " + str(getattr(e, "reason", e))[:120]) from None
            raise LLMError("network", type(e).__name__, retryable=True) from None
        seen.answered = True
        try:
            for data in iter_sse_data(resp.readline):
                if cancel and cancel.cancelled:
                    raise LLMError("cancelled", "cancelled", partial="".join(text_parts))
                if self.clock() - start > total_limit:
                    raise LLMError("timeout", "total time limit", retryable=True, partial="".join(text_parts))
                if '"error"' in data:               # in-band error payload: classified by its business code
                    try:
                        err = json.loads(data).get("error")
                    except (ValueError, AttributeError):
                        err = None
                    if err:
                        e = classify_http(getattr(resp, "status", 200) or 200, data.encode("utf-8"))
                        e.partial = "".join(text_parts)
                        raise e
                try:
                    d = parse_chunk(data)
                except ValueError:
                    continue
                seen.reasoning += len(d.reasoning)
                if d.content:
                    if ttft is None:
                        ttft = self.clock() - t0
                    text_parts.append(d.content)
                    if on_text:
                        on_text(d.content)
                if d.finish_reason:
                    finish = d.finish_reason
                if d.usage:
                    seen.usage = d.usage
        except LLMError:
            raise
        except (socket.timeout, TimeoutError):
            raise LLMError("timeout", "idle timeout", retryable=True, partial="".join(text_parts)) from None
        except _NETWORK_ERRORS as e:
            raise LLMError("network", type(e).__name__, retryable=True, partial="".join(text_parts)) from None
        finally:
            try:
                resp.close()
            except Exception:
                pass
        text = "".join(text_parts)
        if finish == "sensitive":
            raise LLMError("sensitive", "content filtered", partial=text)
        if finish == "network_error":
            raise LLMError("network", "upstream network_error", retryable=True, partial=text)
        if finish is None:
            # A chunked body cut exactly between two chunks (and a fixed-length one cut short) reads as a plain EOF, and
            # the provider always ends a finished stream with a finish_reason chunk: without one the text is incomplete
            # (or empty) and must not look done. Cuts inside a chunk raise instead and are caught above.
            raise LLMError("protocol", "stream ended without finish_reason", retryable=True, partial=text)
        return ChatResult(text=text, finish_reason=finish, usage=seen.usage, ttft=ttft,
                          total=self.clock() - t0, model=model, attempts=attempt, reasoning_chars=seen.reasoning)

    def _meter(self, meter, model: str, seen: _Attempt, request_chars: int) -> None:
        """Bill one answered attempt: the usage the stream carried, else an estimate (prompt ≈ 0.8 × request
        characters, completion ≈ characters received including reasoning)."""
        if seen.usage:
            usage, estimated = seen.usage, False
        else:
            usage = {"prompt_tokens": round(PROMPT_TOKENS_PER_CHAR * request_chars),
                     "completion_tokens": sum(len(p) for p in seen.parts) + seen.reasoning,
                     "completion_tokens_details": {"reasoning_tokens": seen.reasoning}}
            estimated = True
        try:
            meter(model, usage, estimated)
        except Exception as e:          # metering must never hide the call's own result or error
            if self.log:
                self.log({"event": "meter_error", "model": model, "error": f"{type(e).__name__}: {e}"[:200]})

    def _log(self, role, model, res, err, attempts=None):
        if not self.log:
            return
        rec = {"role": role, "model": model}
        if res:
            rec.update(ok=True, ttft=res.ttft, total=res.total, usage=res.usage, attempts=res.attempts,
                       finish=res.finish_reason, chars=len(res.text), reasoning_chars=res.reasoning_chars)
        else:
            rec.update(ok=False, error=err.kind, code=err.code, status=err.status, attempts=attempts)
        self.log(rec)
