"""Generation jobs: the opening (bible + chapter 1) and later chapters.

Two writers share this module's machinery (M3 r3 item 1): Writer(...) is the lean writer (lean.LeanWriter: the baseline's
prompt, one call per chapter cut after its fork; see lean.py) unless the setting writer.mode — or mode= — is "classic":
the r2 pipeline below (director briefs, setups and secret, repairs, structural rewrites), kept for comparison until the
lean writer has passed round 3. The session, the runner and sim.py all build Writer(...), so they follow the setting.
What follows describes the classic writer; lean.py says where the lean one differs.

The writer streams JSON objects from the model, validates each one, repairs locally, applies it to the book it
was given (a private copy when the caller runs it in a thread) and emits Events that let the caller mirror the
change. It never splices other content in: a failure after k pages continues from page k+1 with the committed
pages as fixed context, and pages the caller reports as locked are never rewritten.

Requests per job. The opening: one head stream plus at most one head retry (title, world, setups and as much of
chapter 1 as the stream gives), then at most MAX_ATTEMPTS requests to finish chapter 1 (a continuation stream while
pages are missing, a fork-only request once all exist), a structural rewrite of at most MAX_ATTEMPTS more, up to
three secret-only calls (one retry, then the fallback model) and, for a pool item, the gate call. A chapter:
MAX_ATTEMPTS requests plus the same structural rewrite. Repairs: at most one call per line. Every request first calls
the optional budget hook, none is sent once the caller cancelled, and each is billed through the ledger as the
client's meter (failed attempts included).
WriteFailed kinds: opening, incomplete, cancelled, gate, the fatal client kinds (auth, billing, quota, tls,
bad_request), and — when the bible head failed twice because of the stream — that stream error's kind
(e.g. sensitive, network). An exception in the caller's emit stops the job as EmitFailed (not a WriteFailed: the
mirror lacks a change the writer's book has, so the caller must resync or drop the job's book).

Notes for Plan B (threaded session):
- The lean writer (the default) keeps this contract — the same constructor, opening()/chapter() signatures, Event kinds
  and data, WriteFailed kinds, `done` last — with fewer kinds: opening title, world, page…, choice, done; chapter
  plan_meta, page…, choice or end, done. It never emits setups, secret, reset, plan or truncate, so its choice and end
  are final when they arrive (waiting for done stays right), and `locked` is never needed. A pool opening's gate is code
  only (usage["gate"] "ok", else WriteFailed("gate")). Plan B1's session (rewrite 0071ef8) needs two changes for it
  (M3 r3 review, contract-R3C-1/2; the diff is in the round-3 lean log, #14): it counts a chapter's pages from the
  layout, which a page split in code outgrows (the split-page note below), and it starts siblings 2–3 on sibling 1's
  first event, which is plan_meta, emitted before sibling 1's request: a warm-up that waits for the cache skips it.
- Status is the caller's: book_ops never marks a node done. opening()/chapter() set `done` on the writer's own book
  and emit Event("done") last (carrying node.usage, e.g. the structural outcome). The session marks its node done
  when the job returns; it must not rely on the event alone.
- `choice` and `end` events are provisional until the call returns: the structural check may still truncate the
  chapter and replace its last pages and its fork or ending. node.choice and node.ending of a node that is not done
  must not appear in any view: the fork screen, map doors and labels, option teasers, ending titles (a child's
  ending name on its parent's option card too) and endings lists. Create children and start speculative writing
  only after the job reports done (spec §6.6: "when that node is complete (its fork final)").
  book.endings_found holds the endings the child has read: call book_ops.mark_ending_read when a finale's last page
  is shown.
- The writer asks locked() (pages already shown) before a structural rewrite and again before adopting it; never
  show a chapter's last page before its node is done, so a rewrite never replaces a page the child has seen.
- A `truncate` event drops the pages after `keep` and the rewritten pages reuse their ids (n.A.p3 again): key media
  jobs (pictures, narration) by page revision — the page id plus a hash of its lines — and drop results whose
  revision is gone.
- A page still too long after its repair is split in two (M3 r2): the chapter then has one page more than its layout
  size; the second half has `len.cont` in page.fixes and repeats the first half's art brief (its picture may be
  reused). Count a chapter's pages from node.pages, never from the layout: book_ops.chapter_size(book, node) (the
  layout size plus the second halves; both halves are committed together, so it holds while the chapter streams) for
  the chapter's last page, its next page, the fork and the end, the pages shown before the node is done and the
  finale's last page that marks its ending read; book_ops.page_number(book, node, idx) for the number shown (a second
  half keeps its page's number; the book's last page is still sum(book.chapter_sizes())). With the layout's count the
  chapter's real last page led nowhere and a finale's ending was marked read a page early (M3 r3 review, R3C-1).
- Resume after a failed or interrupted job: chapter() on a node with pages continues from them (quoted verbatim); a
  finale keeps the ending family its pages were written for (node.family, set when it is planned; plan_meta carries it).
  opening() on a book whose bible has setups skips the head (no head events) and continues chapter 1. Head lines
  once shown (title, world) are never reset: a later head stream, also in a new call, quotes them verbatim. The
  title comes first: a world line before it restarts the head (nothing is shown yet), so no book is untitled.
- Pool items (opening(gate=True)): node.usage["gate"] is "ok", or "unchecked" when the gate call failed or gave no
  verdict (logged as a `gate` record with ok None and the error); a failed gate raises WriteFailed("gate"). The pool
  policy decides what an unchecked item gets (another gate call, or served last); it is never a silent pass.
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Callable

from . import book_ops as ops
from . import prompts as P
from . import textutil as tu
from .content import Content
from .costs import Ledger
from .director import ChapterPlan, plan_chapter, render_brief
from .jsonl import JsonObjectStream, loads_lenient
from .llm import CancelToken, ChatClient, LLMError
from .models import BiblePublic, Book, Node
from .validate import (LOG_ONLY, MECHANICAL, ChapterCheck, ForkCtx, PageCtx, Violation, codes, fix_secret, fix_setups,
                       fix_world, hard, last_question, normalize_page, soft_fix_choice, soft_fix_page, split_page,
                       validate_chapter, validate_choice, validate_end, validate_page, validate_secret,
                       validate_setups, validate_title, validate_world)

MODES = ("lean", "classic")
FATAL = frozenset({"auth", "billing", "quota", "tls", "bad_request"})
LINE_ERRORS = (TypeError, ValueError, KeyError, AttributeError, IndexError,   # a malformed line, never a job failure
               RecursionError)
MAX_DEPTH = 8           # a line nested deeper is unreadable: a page needs four levels (page → art → who → an entry)
PAGE_ONE = frozenset({"token.missing", "turn.missing"})      # chapter obligations that belong on the first page
PAGE_TWO = frozenset({"reveal.missing"})                    # the truth has page 2 (the low point's, a twist finale's)
HEAD_RESTART = frozenset({"rule.virtue", "guest.manner", "world.refrain", "head.text",   # left after a world repair
                          "rule.meta", "refrain.trigger"})
EMPTY_SECRET = {"type": "secret", "payoffs": {}, "twists": [], "endings": {}}
GATE_KEYS = ("want_concrete", "rule_not_virtue", "rule_single", "rule_drives_problem", "setups_distinct", "no_moral",
             "guest_manner_ok", "twist_supported")       # rule_single, rule_drives_problem: M3 r2 findings #2 fix 5
GATE_OUTCOME = {True: "ok", False: "failed", None: "unchecked"}           # node.usage["gate"] of a pool item
MAX_ATTEMPTS = 3
SAFER = "请写得更温和、更安全，不要出现吓人或危险的内容。"
REPEAT_SHARE = 0.6      # a streamed page that copies ≥60% of a committed page is a repeat, not a new page


@dataclass
class Event:
    kind: str
    node: str
    data: dict = field(default_factory=dict)


class WriteFailed(Exception):
    def __init__(self, kind: str, message: str = ""):
        super().__init__(f"{kind}: {message}")
        self.kind, self.message = kind, message


class EmitFailed(Exception):
    """The caller's emit raised: its mirror missed a change the writer's book already has, so the job stops here
    (never a rejected line, which would go on from the writer's book while the mirror lacks the change)."""


class _Restart(Exception):
    pass


class _Guard:
    """Cancelled when either the caller's token or the writer's own token is cancelled."""

    def __init__(self, outer: CancelToken | None):
        self.outer, self.own = outer, CancelToken()

    @property
    def cancelled(self) -> bool:
        return self.own.cancelled or bool(self.outer is not None and self.outer.cancelled)

    def cancel(self) -> None:
        self.own.cancel()


@dataclass
class _Job:
    book: Book
    node: Node
    plan: ChapterPlan | None
    brief: str
    emit: Callable[[Event], None]
    cancel: CancelToken | None
    memory_phrases: frozenset
    heads: list = field(default_factory=list)          # opening: title/world lines shown so far (quoted on a retry)
    card: dict | None = None                           # lean opening: the card the book starts from
    unsafe: bool = False                               # lean: this request's stream dropped a line for a safety hit


def _guarded(emit: Callable[[Event], None]) -> Callable[[Event], None]:
    """The caller's emit with its failures as EmitFailed, which is not a LINE_ERROR: a line guard must never swallow
    a failed mirror."""
    def call(e: Event) -> None:
        try:
            emit(e)
        except Exception as x:
            raise EmitFailed(f"{e.kind} {e.node}: {type(x).__name__}: {x}"[:200]) from x
    return call


def _weight(vs: list[Violation]) -> int:
    return sum(10 if v.severity == "hard" else 1 for v in vs)


def _actionable(vs: list[Violation]) -> list[Violation]:
    """Violations worth a fix; LOG_ONLY codes stay on the page as residuals for the metrics."""
    return [v for v in vs if v.code not in LOG_ONLY]


def _better(new: list[Violation], old: list[Violation]) -> bool:
    """A repaired line (or a rewritten chapter) is adopted only if it weighs less and brings no new problem. LOG_ONLY
    codes are measures, never problems: a repair that fixes a real one is not refused for them (M3 r2 review)."""
    new, old = _actionable(new), _actionable(old)
    return _weight(new) < _weight(old) and not set(codes(new)) - set(codes(old))


def _too_deep(obj, limit: int = MAX_DEPTH) -> bool:
    """obj nests dicts and lists more than `limit` levels, counted without recursion: P1 with a field 600 levels deep
    parsed, then normalize_page's deepcopy raised RecursionError (M3 r3 review, R3-ROB-8)."""
    stack = [(obj, 1)]
    while stack:
        o, d = stack.pop()
        if isinstance(o, (dict, list)):
            if d > limit:
                return True
            stack.extend((v, d + 1) for v in (o.values() if isinstance(o, dict) else o))
    return False


def _objects(text: str, complete: bool = True) -> list[dict]:
    """The JSON objects in a whole reply; complete=False (a failed call's partial text) takes closed objects only. One
    nested too deep (_too_deep) is unreadable, like one that does not parse."""
    stream = JsonObjectStream()
    out = stream.feed((text or "") + "\n") + (stream.finish()[0] if complete else [])
    return [o for o in out if isinstance(o, dict) and "__parse_error__" not in o and not _too_deep(o)]


def _first(text: str, kind, complete: bool = True) -> dict | None:
    return next((o for o in _objects(text, complete) if o.get("type") == kind), None)


def _snapshot(node: Node) -> dict:
    return {"state": node.state.to_dict(), "ledger": [x.to_dict() for x in node.ledger]}


def _page_dicts(pages) -> list[dict]:
    return [{"type": "page", "lines": [l.to_dict() for l in p.lines], "delta": p.delta} for p in pages]


def _bible_heads(book: Book) -> list[dict]:
    """Head lines an earlier call already showed (the bible has them): they are quoted, never rewritten."""
    b = book.bible
    out: list[dict] = []
    if b is not None and b.title:
        out.append({"type": "title", "title": b.title, "logline": b.logline})
    if b is not None and b.cast:
        out.append({"type": "world", "hero": b.hero, "cast": list(b.cast), "era": b.era, "want": b.want,
                    "oddity": b.oddity, "rule": dict(b.rule), "guest": dict(b.guest), "antagonist": dict(b.antagonist),
                    "places": list(b.places), "refrain": b.refrain})
    return out


def writer_mode(client, mode: str | None = None) -> str:
    """The writer's mode: `mode` when given, else the client's settings' writer.mode ("lean" by default: config
    DEFAULTS, and also without a client). ValueError for anything else."""
    if mode is None:
        settings = getattr(client, "settings", None)
        mode = settings.get("writer.mode", "lean") if settings is not None else "lean"
    if mode not in MODES:
        raise ValueError(f"unknown writer mode {mode!r}: one of {', '.join(MODES)}")
    return mode


class Writer:
    MODE = "classic"
    CUT_AT_CLOSE = False        # the lean writer stops reading at the chapter's choice or end line
    STREAM_TOKENS = None        # max_tokens of a chapter stream: the role's (the lean writer asks for a whole book)

    def __new__(cls, content: Content, client: ChatClient | None, *args, mode: str | None = None, **kwargs):
        """Writer(...) is lean.LeanWriter unless the mode (writer_mode: mode=, else the settings) is "classic"."""
        if cls is Writer and writer_mode(client, mode) == "lean":
            from .lean import LeanWriter
            cls = LeanWriter
        return super().__new__(cls)

    def __init__(self, content: Content, client: ChatClient, ledger: Ledger | None = None,
                 log: Callable[[dict], None] | None = None, fallback_model: str | None = None,
                 budget: Callable[[], None] | None = None, mode: str | None = None):
        self.c, self.client = content, client
        self.ledger = ledger if ledger is not None else Ledger()
        self.log = log or (lambda rec: None)
        if fallback_model is None:          # not given: the settings' fallback model (config DEFAULTS); "" turns it off
            settings = getattr(client, "settings", None)
            fallback_model = settings.get("fallback_model") if settings is not None else None
        self.fallback_model = fallback_model or None
        self.budget = budget            # raises to refuse the next call (the runner's spending cap)

    # ------------------------------------------------------------ calls
    def _call(self, role, messages, on_text=None, cancel=None, model=None, max_tokens=None):
        """Every request goes through here: the budget hook first, nothing at all once cancelled, and the ledger is
        the client's meter (each answered attempt is billed, failed ones included; a stream cut by the writer from
        what it received)."""
        if self.budget is not None:
            self.budget()
        if cancel is not None and cancel.cancelled:
            raise LLMError("cancelled", "cancelled before the call")
        return self.client.complete(role, messages, on_text=on_text, cancel=cancel, model=model,
                                    max_tokens=max_tokens, meter=self.ledger.add)

    def _stream(self, role: str, messages: list[dict], handle, cancel, model=None) -> LLMError | None:
        """One streaming call; handle(obj) returns False to stop reading. Returns a non-fatal error or None."""
        stream = JsonObjectStream()
        guard = _Guard(cancel)
        stopped = [False]

        def safe(obj) -> bool:
            try:
                if _too_deep(obj):
                    raise ValueError(f"a line nested more than {MAX_DEPTH} levels")
                return handle(obj)
            except LINE_ERRORS as e:            # a validator or fixer choked on an odd line: reject the line
                self.log({"event": "line_error", "role": role, "error": f"{type(e).__name__}: {e}"[:200]})
                return False

        def on_text(chunk):
            if stopped[0]:
                return
            for obj in stream.feed(chunk):
                if not safe(obj):
                    stopped[0] = True
                    guard.cancel()
                    return

        try:
            res = self._call(role, messages, on_text=on_text, cancel=guard, model=model, max_tokens=self.STREAM_TOKENS)
        except LLMError as e:
            caller = cancel is not None and cancel.cancelled
            if e.kind == "cancelled" and stopped[0] and not caller:
                return None
            if e.kind == "cancelled":
                raise WriteFailed("cancelled", "cancelled by the caller")
            if e.kind in FATAL:
                raise WriteFailed(e.kind, e.message)
            self.log({"event": "stream_error", "role": role, "error": e.kind})
            return e
        if stopped[0]:
            return None
        if res.finish_reason == "stop":
            for obj in stream.finish()[0]:      # a last line without its newline; never after a length cut
                if not safe(obj):
                    break
        else:
            self.log({"event": "stream_end", "role": role, "finish": res.finish_reason})
        return None

    def _repair(self, obj: dict, vs: list[Violation], job: _Job) -> dict | None:
        """One repair call on the writer prefix (with the chapter around the line once there is a chapter); the first
        object of the line's type in the reply, or None."""
        vs = _actionable(vs)
        if not vs:
            return None
        try:
            res = self._call("repair", self._repair_messages(obj, vs, job), cancel=job.cancel)
        except LLMError as e:
            if e.kind in FATAL:
                raise WriteFailed(e.kind, e.message)
            if e.kind == "cancelled":
                raise WriteFailed("cancelled", "cancelled by the caller")
            return None
        return _first(res.text, obj.get("type"))

    def _repair_messages(self, obj: dict, vs: list[Violation], job: _Job) -> list[dict]:
        """The repair request: the writer's prefix and, once there is a chapter, the line's surroundings."""
        node = job.node if job.plan is not None else None
        return P.repair_messages(self.c, job.book, job.brief, obj, vs, node=node,
                                 prior=self._prior_pages(job.book, node) if node else (),
                                 committed=list(node.pages) if node else ())

    def _repaired(self, obj: dict, vs: list[Violation], job: _Job, check, prep=None):
        """(line, violations) after one repair: the fixed line only if it is better and brings no new problem."""
        fixed = self._repair(obj, vs, job)
        if fixed is None:
            return obj, vs
        fixed = prep(fixed) if prep else fixed
        vs2 = check(fixed)
        return (fixed, vs2) if _better(vs2, vs) else (obj, vs)

    # ------------------------------------------------------------ settling one line
    def _page_ctx(self, job: _Job) -> PageCtx:
        book, node, plan = job.book, job.node, job.plan
        idx = ops.planned(node.pages) + 1
        ex_ids = set(book.exemplars)
        cast = list(book.bible.cast) + list(node.state.cast_extra)          # cameo voice cards show samples too
        sources = tuple(s for cid in cast if cid in self.c.characters for s in self.c.sample_lines(cid))
        sources += tuple("".join(l["text"] for l in p["lines"]) for p in self.c.examples if p["id"] in ex_ids)
        if book.bible.has_guest() and book.bible.guest.get("manner"):
            sources += (str(book.bible.guest["manner"]),)
        root = book.nodes.get("n")
        first = tuple(l.text for l in root.pages[0].lines) if plan.is_final and root is not None and root.pages else ()
        line = tuple(p.text() for p in list(self._prior_pages(book, node)) + list(node.pages))
        return PageCtx(content=self.c, bible=book.bible, state=node.state, chapter=node.chapter, page_in_chapter=idx,
                       pages_in_chapter=len(plan.pages), is_final_chapter=plan.is_final,
                       chosen=plan.chosen if idx == 1 else None, turn_allowed=plan.is_final,
                       memory_phrases=job.memory_phrases, copy_sources=sources,
                       removed_items=tuple(ops.gone_items(node.state)), ledger=tuple(node.ledger), first_page=first,
                       line=line)

    def _settle_page(self, obj: dict, ctx: PageCtx, job: _Job):
        """Mechanical fixes without a call, else one repair (adopted only if better with no new problem), then the
        substitution fixes; hard problems reject the page. What is left is recorded in _meta.residual."""
        obj = normalize_page(obj)
        vs = validate_page(obj, ctx)
        fixes: list[str] = []
        todo = _actionable(vs)
        if todo and not hard(vs) and set(codes(todo)) <= MECHANICAL:
            obj, fixes = soft_fix_page(obj, vs, ctx)
            vs = validate_page(obj, ctx)
        repaired = False
        if _actionable(vs):
            new, vs2 = self._repaired(obj, vs, job, lambda o: validate_page(o, ctx), normalize_page)
            if new is not obj:
                obj, vs, repaired, fixes = new, vs2, True, []
        if _actionable(vs) and not hard(vs):
            obj, more = soft_fix_page(obj, vs, ctx)
            fixes += more
            vs = validate_page(obj, ctx)
        if hard(vs):
            return None, vs
        obj["_meta"] = {"repaired": repaired, "fixes": fixes, "residual": codes(vs)}
        return obj, vs

    def _split(self, obj: dict, vs: list[Violation], ctx: PageCtx, node: Node) -> list[dict]:
        """A page still past six lines or 6.5 card rows after its repair (`over`) as two pages (validate.split_page, the
        lead's ruling on findings #15: never ship a 7-line page); else the page itself. Each half gets the mechanical
        fixes it needs and its own residuals; the first records len.split, the second len.cont (no planned page of its
        own: ops.planned)."""
        halves = split_page(obj, ctx) if any(v.data.get("over") for v in vs) else None
        if halves is None:
            return [obj]
        meta = obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}
        out = []
        for k, (half, hctx) in enumerate(zip(halves, (ctx, dataclasses.replace(ctx, chosen=None)))):
            hv = validate_page(half, hctx)
            fixes: list[str] = []
            if _actionable(hv) and not hard(hv) and set(codes(_actionable(hv))) <= MECHANICAL:
                half, fixes = soft_fix_page(half, hv, hctx)
                hv = validate_page(half, hctx)
            half["_meta"] = {"repaired": bool(meta.get("repaired")), "residual": codes(hv),
                             "fixes": (list(meta.get("fixes", [])) + ["len.split"] if k == 0 else [ops.CONT]) + fixes}
            out.append(half)
        self.log({"event": "page_split", "node": node.id, "lines": [len(h["lines"]) for h in out]})
        return out

    def _settle_choice(self, obj: dict, fctx: ForkCtx, job: _Job):
        """Code fixes, then one repair (adopted only if better), then a question mark for a q that is still a
        statement (last_question)."""
        obj = soft_fix_choice(obj, self.c)
        vs = validate_choice(obj, fctx)
        if vs:
            obj, vs = self._repaired(obj, vs, job, lambda o: validate_choice(o, fctx),
                                     lambda o: soft_fix_choice(o, self.c))
        if "fork.q_ask" in codes(vs):
            obj = last_question(obj)
            vs = validate_choice(obj, fctx)
        return (None, vs) if hard(vs) else (obj, vs)

    @staticmethod
    def _repeats(obj: dict, pages) -> bool:
        """The streamed page copies ≥ REPEAT_SHARE of one of `pages` (committed pages): a repeat, not a new page."""
        lines = obj.get("lines") if isinstance(obj.get("lines"), list) else []
        text = tu.cjk_only("".join(str(l.get("text", "")) for l in lines if isinstance(l, dict)))
        if not text or not pages:
            return False
        spans = tu.copied_spans(text, [p.text() for p in pages])
        return sum(len(s) for s in spans) >= REPEAT_SHARE * len(text)

    def _repeat_pages(self, job: _Job) -> list:
        """The pages a streamed page must not repeat: this chapter's."""
        return list(job.node.pages)

    @staticmethod
    def _complete(node: Node, plan: ChapterPlan) -> bool:
        tail = node.ending is not None if plan.is_final else node.choice is not None
        return ops.planned(node.pages) >= len(plan.pages) and tail

    @staticmethod
    def _prior_pages(book: Book, node: Node):
        return book.pages_on_path(node.parent) if node.parent else []

    # ------------------------------------------------------------ chapter lines (shared by both jobs)
    def _chapter_obj(self, obj, job: _Job) -> bool:
        book, node, plan = job.book, job.node, job.plan
        if not isinstance(obj, dict) or "__parse_error__" in obj:
            return False
        t = obj.get("type")
        if t == "plan":
            if node.parent is not None and not node.pages and not node.plan:      # chapter 1 has no plan line
                ops.apply_plan(node, obj)
                job.emit(Event("plan", node.id, {"text": node.plan}))
            return True
        if t == "page":
            if self._repeats(obj, self._repeat_pages(job)):             # skipped and logged (M3 r3 review, R3-ROB-4)
                self.log({"event": "repeat", "node": node.id, "page": ops.planned(node.pages) + 1})
                return True
            if ops.planned(node.pages) >= len(plan.pages):  # an extra page: stop; the fork comes alone (_tail)
                self.log({"event": "extra_page", "node": node.id})
                return False
            ctx = self._page_ctx(job)
            settled, vs = self._settle_page(obj, ctx, job)
            if settled is None:
                self.log({"event": "page_rejected", "node": node.id, "codes": codes(vs)})
                return False
            cameos = (settled.get("_meta") or {}).get("cameos")
            if cameos and ops.join_cast(self.c, book, node, cameos):     # lean: a canon character joins the line
                self.log({"event": "cameo", "node": node.id, "cast_extra": list(node.state.cast_extra)})
            for part in self._split(settled, vs, ctx, node):
                page = ops.apply_page(self.c, book, node, part, ctx, plan.clue)
                job.emit(Event("page", node.id, {"page": page.to_dict(), **_snapshot(node)}))
            return True
        if t == "choice" and not plan.is_final:
            if node.choice is not None:
                return True
            if ops.planned(node.pages) < len(plan.pages):
                return False
            fctx = ForkCtx(content=self.c, bible=book.bible, state=node.state, fork_index=node.chapter,
                           is_final_fork=plan.final_fork,
                           page_text="。".join(p.text() for p in book.pages_on_path(node.id)),
                           present=tuple(P.present_names(self.c, book, node.pages[-1])) if node.pages else ())
            settled, vs = self._settle_choice(obj, fctx, job)
            if settled is None:
                self.log({"event": "fork_rejected", "node": node.id, "codes": codes(vs)})
                return False
            cp = ops.apply_choice(book, node, settled, fctx)
            job.emit(Event("choice", node.id, {"choice": cp.to_dict(), **_snapshot(node)}))
            return not self.CUT_AT_CLOSE
        if t == "end" and plan.is_final:
            if node.ending is not None:
                return True
            if ops.planned(node.pages) < len(plan.pages):
                return False
            vs = validate_end(obj, self.c)
            if hard(vs) or {"end.text", "end.title_len"} & set(codes(vs)):     # shown (≤10 字) and read aloud
                self.log({"event": "end_title_fallback", "node": node.id, "codes": codes(vs)})
                obj = {"type": "end", "title": self._end_title(book)}
            ending = ops.apply_end(book, node, obj, plan.ending.get("family", "warm"), content=self.c)
            job.emit(Event("end", node.id, {"ending": ending.to_dict(), **_snapshot(node)}))
            return not self.CUT_AT_CLOSE
        return True

    def _end_title(self, book: Book) -> str:
        """The ending's name when the end line's cannot be shown: the first of the book's title, the card's and 「完」 that
        passes validate_end with no code — never cut ([:10] made 「熊二捡到一朵会打喷嚏」), never with the problem that sent
        the end line here (M3 r3 review, R3-ROB-6: 「吓死人的小云朵」, 「The Sneezi」)."""
        titles = [book.bible.title if book.bible is not None else "", book.premise.get("title")]
        return next((t for t in titles if isinstance(t, str) and t.strip()
                     and not validate_end({"type": "end", "title": t}, self.c)), "完")

    def _finish_chapter(self, job: _Job, note: str = "") -> None:
        """Up to MAX_ATTEMPTS requests until the chapter has its pages and its fork (or end): a stream while pages are
        missing (continuing after the committed ones), else the fork alone (_tail). The request after a sensitive stop,
        or after one whose line the lean writer dropped for a safety hit (job.unsafe, M3 r3 review R3-ROB-7), says SAFER."""
        attempts = failures = 0
        extra = ""
        while not self._complete(job.node, job.plan):
            attempts += 1
            if attempts > MAX_ATTEMPTS:
                raise WriteFailed("incomplete", f"node {job.node.id} incomplete after {MAX_ATTEMPTS} streams")
            model = self.fallback_model if failures >= 2 and self.fallback_model else None
            notes = "".join(dict.fromkeys(x for x in (note, extra) if x))
            job.unsafe = False
            if ops.planned(job.node.pages) >= len(job.plan.pages):
                err = self._tail(job, notes, model)
            else:
                err = self._stream("chapter", self._chapter_messages(job, notes), lambda o: self._chapter_obj(o, job),
                                   job.cancel, model=model)
            if err is not None and err.kind != "sensitive":
                failures += 1
            extra = SAFER if (err is not None and err.kind == "sensitive") or job.unsafe else ""

    def _chapter_messages(self, job: _Job, note: str) -> list[dict]:
        """A chapter stream, or its continuation after the committed pages."""
        return P.chapter_messages(self.c, job.book, job.node, job.plan, job.brief, self._prior_pages(job.book, job.node),
                                  committed=list(job.node.pages), note=note)

    def _tail(self, job: _Job, note: str, model) -> LLMError | None:
        """The fork (or the end line) alone once every page exists: one request that is not read as a stream; the first
        object of the wanted type in the reply (or in a failed call's partial text) is settled like a streamed one."""
        book, node, plan = job.book, job.node, job.plan
        want = "end" if plan.is_final else "choice"
        msgs = P.tail_messages(self.c, book, node, plan, job.brief, self._prior_pages(book, node), list(node.pages),
                               note=note)
        err, complete = None, True
        try:
            text = self._call("chapter", msgs, cancel=job.cancel, model=model).text
        except LLMError as e:
            if e.kind == "cancelled":
                raise WriteFailed("cancelled", "cancelled by the caller")
            if e.kind in FATAL:
                raise WriteFailed(e.kind, e.message)
            self.log({"event": "stream_error", "role": "chapter", "error": e.kind, "tail": True})
            text, err, complete = e.partial, e, False
        obj = _first(text, want, complete)
        if obj is None:
            self.log({"event": "tail_missing", "node": node.id, "want": want})
            return err
        try:
            self._chapter_obj(obj, job)
        except LINE_ERRORS as e:
            self.log({"event": "line_error", "role": "chapter", "error": f"{type(e).__name__}: {e}"[:200],
                      "tail": True})
        return err

    @staticmethod
    def _outcome(node: Node, outcome: str, vs=()) -> None:
        """node.usage["structural"] = ok|fixed|no_better|unfixable|failed|discarded, with the codes still missing."""
        node.usage["structural"] = outcome
        node.usage["structural_codes"] = codes(list(vs))

    def _structural(self, job: _Job, locked: Callable[[], int]) -> None:
        """Chapter-level checks. A miss is rewritten from the page it belongs on: the chosen token (and the finale's
        turn) on page 1 — only while nothing is shown —, the truth (reveal.missing) from planned page 2, never before
        locked(), other misses (payoffs, rule use, plants) from the last planned page (both halves of a split page),
        never before locked(). The rewrite is adopted only if it fully succeeds, is better and brings no new miss, and the
        reader has not reached it meanwhile."""
        book, node, plan = job.book, job.node, job.plan
        check = ChapterCheck(self.c, book.bible, due_payoffs=tuple(plan.due_payoffs),
                             must_plant=tuple(plan.must_plant), token=plan.chosen.token if plan.chosen else "",
                             is_finale=plan.is_final, needs_rule=plan.needs_rule, ledger=tuple(node.ledger),
                             option_text=plan.chosen.text if plan.chosen else "", reveal=plan.reveal)
        vs = validate_chapter(_page_dicts(node.pages), check)
        if not vs:
            return self._outcome(node, "ok")
        shown = int(locked())
        if set(codes(vs)) & PAGE_ONE:
            keep = 0 if shown == 0 else len(node.pages)
        elif set(codes(vs)) & PAGE_TWO:
            keep = max(shown, ops.start_of(node.pages, 1))
        else:                                    # from the last planned page (a split page counts as one)
            keep = max(shown, ops.start_of(node.pages, ops.planned(node.pages) - 1))
        self.log({"event": "structural", "node": node.id, "codes": codes(vs), "keep": keep})
        if keep >= len(node.pages):
            self.log({"event": "structural_unfixable", "node": node.id, "codes": codes(vs), "locked": shown})
            return self._outcome(node, "unfixable", vs)
        trial = copy.deepcopy(book)
        tnode = trial.nodes[node.id]
        ops.truncate(self.c, trial, tnode, keep, plan.clue)
        events: list[Event] = []
        tjob = _Job(trial, tnode, plan, job.brief, events.append, job.cancel, job.memory_phrases)
        try:
            self._finish_chapter(tjob, note="这一章还需要做到：" + "；".join(v.message for v in vs))
        except WriteFailed as e:
            if e.kind in FATAL or e.kind == "cancelled":
                raise
            self.log({"event": "structural_failed", "node": node.id, "error": e.kind})
            return self._outcome(node, "failed", vs)
        new = validate_chapter(_page_dicts(tnode.pages), check)
        if not _better(new, vs):
            self.log({"event": "structural_no_better", "node": node.id, "codes": codes(new)})
            return self._outcome(node, "no_better", vs)
        if int(locked()) > keep:          # the reader got there first: keep what was shown
            self.log({"event": "structural_discarded", "node": node.id})
            return self._outcome(node, "discarded", vs)
        ops.truncate(self.c, book, node, keep, plan.clue)
        job.emit(Event("truncate", node.id, {"keep": keep, **_snapshot(node)}))
        for e in events:
            ops.apply_event(self.c, book, e)
            job.emit(e)
        self._outcome(node, "fixed", new)

    # ------------------------------------------------------------ opening
    def _show_head(self, job: _Job, obj: dict) -> None:
        job.emit(Event(obj["type"], "n", obj))
        job.heads.append(obj)

    def _opening_obj(self, obj, job: _Job) -> bool:
        book = job.book
        if not isinstance(obj, dict) or "__parse_error__" in obj:
            if job.plan is None:
                raise _Restart("unparseable bible head")
            return False
        t = obj.get("type")
        if t == "title":
            if book.bible is not None and book.bible.title:
                return True
            vs = validate_title(obj, self.c)
            if not hard(vs) and "head.text" in codes(vs):          # the title is shown: one repair for its wording
                obj, vs = self._repaired(obj, vs, job, lambda o: validate_title(o, self.c))
            if hard(vs) or "head.text" in codes(vs):
                raise _Restart("bad title: " + ",".join(codes(vs)))
            ops.apply_title(book, obj)
            self._show_head(job, obj)
            return True
        if t == "world":
            if book.bible is not None and book.bible.cast:
                return True
            if book.bible is None or not book.bible.title:          # the birth screen and the shelf need a title
                raise _Restart("world before the title")
            fixed = fix_world(obj, self.c)                          # shapes and words fixed in code, like fix_setups
            changed = sorted(k for k in set(obj) | set(fixed) if obj.get(k) != fixed.get(k))
            if changed:                                             # recorded (M3 r2 #6: the cast cleaned)
                rec = {"event": "world_fixed", "fields": changed}
                if {"cast", "hero"} & set(changed):
                    rec.update(cast=obj.get("cast"), hero=obj.get("hero"), now=fixed.get("cast"),
                               now_hero=fixed.get("hero"))
                self.log(rec)
            obj = fixed
            vs = validate_world(obj, self.c)
            if vs:
                obj, vs = self._repaired(obj, vs, job, lambda o: validate_world(o, self.c),
                                         lambda o: fix_world(o, self.c))
            if hard(vs) or set(codes(vs)) & HEAD_RESTART:          # no page exists yet: a fresh world is cheap
                raise _Restart("bad world: " + ",".join(codes(vs)))
            ops.apply_world(book, obj, self.c)
            self._show_head(job, obj)
            return True
        if t == "setups":
            if job.plan is not None or (book.bible is not None and book.bible.setups):
                return True
            if book.bible is None or not book.bible.cast:
                raise _Restart("setups before the world")
            obj = fix_setups(obj, self.c)                           # shapes and words fixed in code
            vs = validate_setups(obj, self.c)
            if hard(vs) or "setups.text" in codes(vs):              # one quick repair (before any restart): every
                obj, vs = self._repaired(obj, vs, job, lambda o: validate_setups(o, self.c),     # brief quotes them
                                         lambda o: fix_setups(o, self.c))
            if hard(vs):
                raise _Restart("bad setups: " + ",".join(codes(vs)))
            ops.apply_setups(book, obj)
            job.emit(Event("setups", "n", obj))
            job.plan = plan_chapter(self.c, book, 1)
            job.brief = P.opening_brief(self.c, job.plan)
            return True
        if t == "secret":
            if job.plan is not None and book.secret is None:
                self._apply_secret(job, obj)
            return True
        if t in ("page", "choice"):
            if job.plan is None:
                raise _Restart("chapter text before the bible head")
            return self._chapter_obj(obj, job)
        return True

    def _apply_secret(self, job: _Job, obj: dict) -> None:
        """The secret after fix_secret (its words swapped, a part with a safety or adult problem dropped): the briefs
        quote it to the writer. The codes of the line as it came and the fixes are logged."""
        book = job.book
        vs = validate_secret(obj, {s.get("id") for s in book.bible.setups}, self.c)
        obj, fixes = fix_secret(obj, self.c)
        obj = ops.mark_card_twist(self.c, book, obj)          # the card's truth, put first, binds two branches
        ops.apply_secret(book, obj)
        self.log({"event": "secret", "codes": codes(vs), "twists": len(book.secret.twists),
                  **({"fixes": fixes} if fixes else {})})
        job.emit(Event("secret", "n", obj))

    def _ensure_secret(self, job: _Job) -> None:
        """The secret line when the opening stream did not deliver it: a secret-only call, one retry, then the fallback
        model; the first `secret` object of a reply counts (the model may repeat a page first). Without one the book
        gets an empty secret (no twist, no ending templates) instead of failing."""
        book = job.book
        if book.secret is not None:
            return
        for model in [None, None] + ([self.fallback_model] if self.fallback_model else []):
            complete = True
            try:
                text = self._call("bible", P.secret_messages(self.c, book), cancel=job.cancel, model=model).text
            except LLMError as e:
                if e.kind in FATAL:
                    raise WriteFailed(e.kind, e.message)
                if e.kind == "cancelled":
                    raise WriteFailed("cancelled", "cancelled by the caller")
                self.log({"event": "secret_error", "error": e.kind})
                text, complete = e.partial, False
            obj = _first(text, "secret", complete)
            if obj is not None:
                return self._apply_secret(job, obj)
            self.log({"event": "secret_missing", "model": model})
        self.log({"event": "secret_empty"})
        self._apply_secret(job, dict(EMPTY_SECRET))

    def _gate(self, book: Book, cancel) -> bool | None:
        """The pool gate (G1): True passed, False failed (a checklist key is false), None unchecked — the call failed
        or its reply gave no verdict (no JSON object, or a key missing or not true/false). Every outcome is logged."""
        heads = {"title": book.bible.title, "world": book.bible.to_dict(),
                 "secret": book.secret.to_dict() if book.secret else {}}
        try:
            verdict = loads_lenient(self._call("gate", P.gate_messages(self.c, heads), cancel=cancel).text)
        except LLMError as e:
            if e.kind in FATAL:
                raise WriteFailed(e.kind, e.message)
            if e.kind == "cancelled":
                raise WriteFailed("cancelled", "cancelled by the caller")
            self.log({"event": "gate", "ok": None, "error": e.kind})
            return None
        except ValueError:
            self.log({"event": "gate", "ok": None, "error": "unreadable"})
            return None
        vals = [verdict.get(k) for k in GATE_KEYS]
        ok = False if any(v is False for v in vals) else (True if all(v is True for v in vals) else None)
        self.log({"event": "gate", "ok": ok, "problems": verdict.get("problems", []),
                  **({"error": "unreadable"} if ok is None else {})})
        return ok

    def _head_brief(self, book: Book, card: dict) -> str:
        temp = copy.deepcopy(book)
        if temp.bible is None or not temp.bible.cast:
            temp.bible = BiblePublic(hero=card["cast"][0], cast=list(card["cast"]))
        return P.opening_brief(self.c, plan_chapter(self.c, temp, 1))

    def _head(self, book: Book, card: dict, emit, cancel, memory_phrases: frozenset) -> tuple[_Job, str]:
        """The bible head (title, world, setups) and as much of chapter 1 as the stream gives: one stream and at most
        one retry. Once a head line was shown it is never reset: the retry quotes the shown lines verbatim and
        continues from the next one (with SAFER after a sensitive stop); only when nothing was shown does it start
        clean."""
        root = book.nodes["n"]
        heads = _bible_heads(book)
        note, cause = "", None
        for _attempt in range(2):
            job = _Job(book, root, None, self._head_brief(book, card), emit, cancel, memory_phrases, heads=heads)
            try:
                msgs = P.opening_messages(self.c, book, card, job.brief, heads=tuple(heads), note=note)
                err = self._stream("bible", msgs, lambda o: self._opening_obj(o, job), cancel)
            except _Restart as r:
                if root.pages:
                    raise WriteFailed("opening", str(r))
                cause, note = None, ""
                self.log({"event": "opening_restart", "reason": str(r), "shown": [h.get("type") for h in heads]})
            else:
                if job.plan is not None:
                    return job, SAFER if err is not None and err.kind == "sensitive" else ""
                cause, note = err, SAFER if err is not None and err.kind == "sensitive" else ""
                self.log({"event": "opening_retry", "error": err.kind if err else None,
                          "shown": [h.get("type") for h in heads]})
            if not heads and book.bible is not None:          # nothing shown: a clean start
                ops.reset_opening(book)
                emit(Event("reset", "n"))
        if cause is not None:
            raise WriteFailed(cause.kind, cause.message)
        raise WriteFailed("opening", "the bible head failed twice")

    def opening(self, book: Book, card: dict, emit=None, cancel=None, memory_phrases=frozenset(),
                gate: bool = False, locked: Callable[[], int] = lambda: 0) -> Book:
        """Writes the bible and chapter 1. A book whose bible already has setups resumes: no head stream and no head
        events; chapter 1 continues from its committed pages, then the structural check and the secret."""
        emit = _guarded(emit or (lambda e: None))          # a failed mirror stops the job (EmitFailed)
        root = book.nodes["n"]
        root.status = "streaming"
        job, note = self._begin_opening(book, card, emit, cancel, frozenset(memory_phrases))
        self._finish_chapter(job, note=note)
        self._end_opening(job, locked, gate, cancel)
        root.status = "done"
        emit(Event("done", "n", {"usage": dict(root.usage)}))
        return book

    def _begin_opening(self, book: Book, card: dict, emit, cancel, mem: frozenset) -> tuple[_Job, str]:
        """The opening's job and the note for chapter 1's requests: the bible head stream, or a resume."""
        b = book.bible
        if b is not None and b.cast and b.setups:
            plan = plan_chapter(self.c, book, 1)
            self.log({"event": "opening_resume", "pages": len(book.nodes["n"].pages)})
            return _Job(book, book.nodes["n"], plan, P.opening_brief(self.c, plan), emit, cancel, mem), ""
        return self._head(book, card, emit, cancel, mem)

    def _end_opening(self, job: _Job, locked: Callable[[], int], gate: bool, cancel) -> None:
        """Once chapter 1 has its pages and fork: the structural check, the secret and, for a pool item, the gate."""
        self._structural(job, locked)
        self._ensure_secret(job)
        if gate:
            ok = self._gate(job.book, cancel)
            job.node.usage["gate"] = GATE_OUTCOME[ok]
            if ok is False:
                raise WriteFailed("gate", "the bible failed the gate")

    def chapter(self, book: Book, node_id: str, emit=None, cancel=None, locked: Callable[[], int] = lambda: 0,
                memory_phrases=frozenset(), memory_families=()) -> Book:
        emit = _guarded(emit or (lambda e: None))          # a failed mirror stops the job (EmitFailed)
        node = book.nodes[node_id]
        if node.parent is None:
            raise ValueError("the root chapter is written by opening()")
        parent = book.nodes[node.parent]
        chosen = parent.choice.option(node.via) if parent.choice else None
        resumed = node.family if node.pages else ""      # a resumed finale keeps the family its pages were written for
        plan = plan_chapter(self.c, book, node.chapter, parent, chosen, memory_phrases, memory_families, family=resumed)
        if plan.is_final:
            node.family = plan.ending.get("family", "")
        node.role, node.outcome, node.status = plan.role, plan.outcome, "streaming"
        emit(Event("plan_meta", node_id, {"role": plan.role, "outcome": plan.outcome, "family": node.family}))
        job = _Job(book, node, plan, self._brief(plan, book), emit, cancel, frozenset(memory_phrases))
        self._finish_chapter(job)
        self._end_chapter(job, locked)
        node.status = "done"
        emit(Event("done", node_id, {"usage": dict(node.usage)}))
        return book

    def _brief(self, plan: ChapterPlan, book: Book) -> str:
        return render_brief(plan, self.c, book)

    def _end_chapter(self, job: _Job, locked: Callable[[], int]) -> None:
        """Once the chapter has its pages and fork (or end): the structural check."""
        self._structural(job, locked)
