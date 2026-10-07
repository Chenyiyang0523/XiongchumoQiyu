"""Offline harness (scratch, review only): the real plan-B1 Session (rewrite's session.py, jobs.py, library.py, …
overlaid on m3-r2 HEAD) driving the real lean writer (Writer(...) → LeanWriter) through a ChatClient on a routing fake
transport that answers each request by what it asks for (the opening, chapter N, a continuation after k pages, a tail,
a repair, an idea), so the session's own scheduling (speculation, preemption, retries) decides the order."""
import json
import re
import threading
import time

from fakes import LAMP_IDEA, LEAN_CHAPTERS, LEAN_HEAD, sse
from helpers import C
from sessfakes import WALL, AutoWeb, Clock
from xcmengine import prompts as P
from xcmengine.config import Settings
from xcmengine.images import ImageClient
from xcmengine.jobs import Jobs
from xcmengine.library import Library
from xcmengine.llm import ChatClient, HTTPStatusError, _FakeResponse
from xcmengine.session import Session
from xcmengine.tts import SayEngine, SpeechClient

IDEA_SYS = "\n".join(C.style["idea_system"])
CN = "零一二三四五六七八九"


def _num(s: str) -> int:
    return 2 if s == "两" else CN.index(s)


class BlockingResponse(_FakeResponse):
    """Serves `n` data lines, then waits (≤ 10 s) for `gate` before serving the rest."""

    def __init__(self, text, n, gate, reached):
        super().__init__(text)
        self._n, self._gate, self._reached = n, gate, reached

    def readline(self):
        line = super().readline()
        if line.startswith(b"data:") and self._data_seen == self._n + 1:
            self._reached.set()
            self._gate.wait(10.0)
        return line


class Router:
    """Answers lean requests by their content. overrides: [(predicate(info) -> bool, step)] used once each, where step
    is ("sse", text) | ("drop", text, n) | ("http", status, body) | ("block", text, n, gate, reached)."""

    def __init__(self, chapters=LEAN_CHAPTERS, head=LEAN_HEAD, idea=LAMP_IDEA, repair=None):
        self.chapters, self.head, self.idea, self.repair = chapters, head, idea, repair
        self.requests: list[dict] = []
        self.overrides: list = []
        self.lock = threading.Lock()
        self.advance = None

    @staticmethod
    def classify(body: dict) -> dict:
        msgs = body["messages"]
        system, user = msgs[0]["content"], msgs[-1]["content"]
        if system == IDEA_SYS:
            return {"kind": "idea", "user": user}
        if "【要修改的这一行】" in user:
            return {"kind": "repair", "user": user,
                    "line": json.loads(user.split("【要修改的这一行】\n")[1].split("\n")[0])}
        if "【这次请一次写完整本书】" in user:
            return {"kind": "opening", "user": user}
        m = re.search(r"现在写第(.)章", user)
        ch = _num(m.group(1))
        if "不要再写 page 行" in user:
            k = _num(re.search(r"这一章的(.)页已经全部写完", user).group(1))
            return {"kind": "tail", "chapter": ch, "k": k, "user": user}
        r = re.search(r"这一章已经写好(.)页", user)
        if r:
            return {"kind": "resume", "chapter": ch, "k": _num(r.group(1)), "user": user}
        return {"kind": "chapter", "chapter": ch, "user": user}

    def rest(self, n: int) -> list:
        return [o for ch in self.chapters[n - 1:] for o in ch]

    def answer(self, info: dict) -> str:
        kind = info["kind"]
        if kind == "idea":
            return sse(self.idea)
        if kind == "repair":
            return sse(self.repair(info) if self.repair else info["line"])
        if kind == "opening":
            return sse(self.head, *self.rest(1))
        ch = info["chapter"]
        objs = self.chapters[ch - 1]
        pages = [o for o in objs if o["type"] == "page"]
        tail = [o for o in objs if o["type"] != "page"]
        if kind == "tail":
            return sse(*tail)
        if kind == "resume":
            return sse(*pages[info["k"]:], *tail, *self.rest(ch + 1))
        return sse(*self.rest(ch))

    def post(self, url, headers, body, timeout):
        b = json.loads(body)
        info = self.classify(b)
        info["body"] = b
        with self.lock:
            self.requests.append(info)
            step = None
            for i, (pred, st) in enumerate(self.overrides):
                if pred(info):
                    step = st
                    self.overrides.pop(i)
                    break
        if step is None:
            return _FakeResponse(self.answer(info))
        if step[0] == "sse":
            return _FakeResponse(step[1])
        if step[0] == "drop":
            return _FakeResponse(step[1], drop_after=step[2])
        if step[0] == "http":
            raise HTTPStatusError(step[1], step[2].encode("utf-8"))
        if step[0] == "block":
            return BlockingResponse(step[1], step[2], step[3], step[4])
        raise AssertionError(step)

    def kinds(self):
        return [(r["kind"], r.get("chapter")) for r in self.requests]


class Capture:
    """Wraps the session's own default writer factory: records each writer (type), its book copy after the job and the
    events in the order the session applies them."""

    def __init__(self, s: Session):
        self.s, self.default = s, s.writer_factory
        self.writers, self.copies, self.events, self.cards = [], {}, [], []
        s.writer_factory = self.factory
        orig = s._apply_text_event

        def apply(book, ev, job):
            self.events.append((job.key, ev.kind, ev.node, sorted(ev.data)))
            return orig(book, ev, job)
        s._apply_text_event = apply

    def factory(self, ledger):
        w = self.default(ledger)
        self.writers.append(w)
        op, ch = w.opening, w.chapter

        def opening(book, card, **kw):
            self.cards.append(dict(card))
            try:
                return op(book, card, **kw)
            finally:
                self.copies.setdefault("n", []).append(book)

        def chapter(book, node_id, **kw):
            try:
                return ch(book, node_id, **kw)
            finally:
                self.copies.setdefault(node_id, []).append(book)
        w.opening, w.chapter = opening, chapter
        return w

    def job_events(self, node_id):
        return [k for (key, k, n, _) in self.events if n == node_id]


def make(tmp_path, router=None, threaded=False, prefs=None, limits=None, data="data"):
    lib = Library(tmp_path / data, clock=lambda: WALL)
    lib.set_prefs(**{"pool_size": 0, **(prefs or {})})
    settings = Settings({"retries": 1}, env={})
    router = router or Router()
    web = AutoWeb()
    clock, logs = Clock(), []
    chat = ChatClient(settings, transport=router, api_key="K", sleep=lambda s: None)
    s = Session(lib, settings, content=C, chat=chat,
                images=ImageClient(settings, web=web, api_key="K", sleep=lambda s: None),
                speech=SpeechClient(settings, web=web, api_key="K", say=SayEngine(platform="linux"), sleep=lambda s: None),
                jobs=Jobs({"text": 3, "image": 3, "tts": 2, **(limits or {})}, threaded=threaded, clock=clock),
                clock=clock, wall=lambda: WALL, log=logs.append)
    cap = Capture(s)
    s.test = {"router": router, "logs": logs, "clock": clock, "cap": cap, "web": web}
    return s


def settle(s, max_steps=4000):
    for _ in range(max_steps):
        s.poll()
        if not s.jobs.step():
            s.poll()
            if not s.jobs.step():
                return s
    raise AssertionError("the session did not settle")


def until(s, cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s.poll()
        if cond():
            return True
        time.sleep(0.01)
    raise AssertionError("timed out")


def bad_logs(s):
    return [r for r in s.test["logs"] if r.get("event") in ("mirror_failed", "poll_error", "text_failed")]


def node_core(node) -> dict:
    """What the writer owns of a node (the session owns status, read, speculative, error and the media refs)."""
    d = node.to_dict()
    for p in d["pages"]:
        p.pop("image", None)
        p.pop("audio", None)
    for k in ("status", "read", "speculative", "error", "error_kind"):
        d.pop(k, None)
    return d


def read_chapter(s, bid, nid):
    for p in s.node_view(bid, nid)["pages"]:
        s.page_shown(bid, p)
