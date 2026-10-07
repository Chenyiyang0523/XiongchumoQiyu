"""The lean writer (M3 r3): the baseline's prompt, one chapter per call, the stream cut after the chapter's fork.

Why (plan m3-r3-lean.md): the r2 pipeline — director briefs, obligations, setups and secret, validators with repairs,
structural rewrites — lost every blind comparison to tools/baseline.py, which writes a whole book in one call. The lean
prototype (tools/lean_proto.py) kept the game's shape (one chapter per call, the child picks at each fork) but asked the
way the baseline asks; it reached the baseline and beat the r2 pipeline almost every time. LeanWriter is that prototype
on the classic writer's machinery (writer.Writer: streaming, line settling, splitting, continuation, events, the meter,
the budget hook, cancel); Writer(...) gives it unless the setting writer.mode says "classic".

- opening(): one streamed call, prompts.lean_opening_messages (the baseline's whole-book request, its first line the
  extended title line), cut right after the first choice line; the model's own "chosen" is ignored. The title line,
  after validate.fix_head and one repair for a safety hit (a part that keeps a hard one is dropped), becomes the minimal
  bible: book_ops.head_lines, shown as a title and a world event. A page before any title line takes the card's head;
  a call that brings neither a title line nor a page is sent once more (with SAFER after a sensitive stop). A pool
  opening's gate is code only: a title, at least two pages and a fork (no gate call). Resuming (the bible has a title):
  chapter 1 goes on from its committed pages.
- chapter(): the classic flow without the brief and the structural check — plan_meta (the director's outcome variant,
  and the finale's ending family), then one streamed call, prompts.lean_messages (the book so far as JSON lines, the
  prototype's continuation, the picked option's consequence, a sibling's outcome variant or a child's idea, the
  finale's family), cut right after the node's choice line, or its end line in the last chapter; the ending takes the
  director's family whatever the end line says (a different one is logged as end_family).
- Lines (validate.py's lean profile): every protection that is code — format, who is on the page (lean_fix_page),
  script, voice, quotes, the picture's speakers, Tier B and the fixed replacements, the fork question, a page past six
  lines or 6.5 card rows split in two (Writer._split) — and one repair for a safety hit (LEAN_SAFETY; a fork gets it for
  a hard problem too): a hard hit left after it drops the line, the stream stops there, and the next request goes on
  from the last committed page. A canon character outside the cast joins the world line (state.cast_extra). A line of
  an odd type is read by its shape (a lines list is a page, an opts list a fork; one that cannot be read stops the
  stream); a plan line, a head line written again and any other type are dropped and the stream goes on. No plant,
  payoff, turn, token, ack, reveal or rule checks (their codes stay residuals, for the metrics) and no structural
  rewrite: never a truncate. A fork whose q or option text the child could not be shown (no q, Latin letters left) is
  treated like a hard problem; the request after a line dropped for a safety hit says SAFER (M3 r3 review).
- Requests (Writer._finish_chapter): while pages are missing, the same request with the committed pages in the book so
  far and 「接着写第N页」; once all exist (a page beyond the chapter's count stops a stream), the fork or the end line alone,
  streamed and cut too. At most MAX_ATTEMPTS per chapter, the fallback model on the third, the budget hook before
  every request, none once the caller cancelled, every answered attempt billed (a cut stream from what it received).
Events, in the order plan B1's session mirrors them: opening title, world, page…, choice, done; chapter plan_meta,
page…, choice or end, done (with node.usage). Never setups, secret, reset, plan or truncate.
"""
from __future__ import annotations

from typing import Callable

from . import book_ops as ops
from . import freetext as ft
from . import prompts as P
from .director import ChapterPlan, plan_chapter
from .llm import LLMError
from .models import Book
from .validate import (LEAN_SAFETY, MECHANICAL, ForkCtx, PageCtx, Violation, codes, drop_head_parts, fix_head, hard,
                       last_question, lean_check_page, soft_fix_choice, validate_choice, validate_head)
from .writer import SAFER, Event, WriteFailed, Writer, _Job

LEAN_MAX_TOKENS = 8000      # baseline.py's room for the whole book its request asks for; the stream is cut after one chapter
HEAD_TYPES = ("title", "world", "setups", "secret", "plan")          # lines of these types are never read by shape


def _unshown(vs: list[Violation]) -> list[Violation]:
    """A fork's q or option text the child could not be shown or read aloud (B1 reads the question and the labels): no
    q (fork.q) or Latin letters left in it or in an option's text (fork.script on q or on the text) — like a hard
    problem: one repair, then the fork is dropped (M3 r3 review, R3-ROB-3 and R3-ROB-5)."""
    return [v for v in vs if v.code == "fork.q" or (v.code == "fork.script" and (v.where == "q" or v.data.get("text")))]


def _grave(vs: list[Violation]) -> list[Violation]:
    """What a lean line never ships with: its hard problems and, on a fork, what the child could not be shown."""
    return hard(vs) + [v for v in _unshown(vs) if v.severity != "hard"]


def _lean_weight(vs: list[Violation]) -> int:
    """What one lean repair must lower: its safety hits and grave problems (a grave one weighs 10)."""
    grave = _grave(vs)
    return 10 * len(grave) + sum(1 for v in vs if v.code in LEAN_SAFETY and v not in grave)


def _safer(new: list[Violation], old: list[Violation]) -> bool:
    """A repaired lean line is taken only if it weighs less and brings no new grave problem."""
    return _lean_weight(new) < _lean_weight(old) and not set(codes(_grave(new))) - set(codes(_grave(old)))


class LeanWriter(Writer):
    MODE = "lean"
    CUT_AT_CLOSE = True
    STREAM_TOKENS = LEAN_MAX_TOKENS

    # ------------------------------------------------------------ the opening
    def _begin_opening(self, book: Book, card: dict, emit, cancel, mem: frozenset) -> tuple[_Job, str]:
        root = book.nodes["n"]
        if book.premise.get("avoid") and not card.get("avoid"):     # the session rebuilds the card without it: every
            card = dict(card, avoid=list(book.premise["avoid"]))     # request of the book shows the same card block
        job = _Job(book, root, plan_chapter(self.c, book, 1), "", emit, cancel, mem, card=card)
        if book.bible is not None and book.bible.title:            # a resumed opening: its head was shown
            self.log({"event": "opening_resume", "pages": len(root.pages)})
            return job, ""
        note, err = "", None
        for _attempt in range(2):
            job.unsafe = False
            err = self._stream("bible", P.lean_opening_messages(self.c, book, card, note=note),
                               lambda o: self._opening_obj(o, job), cancel)
            note = SAFER if (err is not None and err.kind == "sensitive") or job.unsafe else ""
            if book.bible is not None and book.bible.title:
                return job, note
            self.log({"event": "opening_retry", "error": err.kind if err else None})
        if err is not None:
            raise WriteFailed(err.kind, err.message)
        raise WriteFailed("opening", "two calls brought neither a title line nor a page")

    def _end_opening(self, job: _Job, locked: Callable[[], int], gate: bool, cancel) -> None:
        """A pool item's gate is code only (item 2): a title, two pages or more and a fork of two options or more."""
        if not gate:
            return
        root, b = job.node, job.book.bible
        ok = (b is not None and bool(b.title) and len(root.pages) >= 2 and root.choice is not None
              and len(root.choice.options) >= 2)
        root.usage["gate"] = "ok" if ok else "failed"
        self.log({"event": "gate", "ok": ok, "code_only": True})
        if not ok:
            raise WriteFailed("gate", "the opening has no title, fewer than two pages or no fork")

    def _opening_obj(self, obj, job: _Job) -> bool:
        """The opening stream: the title line (once), then chapter 1's lines. A line before the head that cannot be
        read is skipped (it may have been the title line); a page or fork before any title line takes the card's
        head first."""
        b = job.book.bible
        has_head = b is not None and bool(b.title)
        readable = isinstance(obj, dict) and "__parse_error__" not in obj
        if readable:
            obj = self._shaped(obj, "n")
            if obj is None:
                return False
        t = obj.get("type") if readable else None
        if not has_head:
            if t == "title":
                self._show_head(job, self._settle_head(obj, job))
                return True
            if t not in ("page", "choice", "end"):
                self.log({"event": "line_dropped", "node": "n", "type": str(t)[:20] if readable else "unreadable"})
                return True
            self.log({"event": "head_from_card", "first": t})
            self._show_head(job, self._card_head(job.card or {}))
        return self._chapter_obj(obj, job)

    def _card_head(self, card: dict) -> dict:
        return fix_head({"title": str(card.get("title") or "")}, self.c, card)

    def _settle_head(self, obj: dict, job: _Job) -> dict:
        """fix_head, then one repair for a safety hit (taken only if safer); a part still carrying a hard hit goes
        (drop_head_parts). A missing title is the card's."""
        card = job.card or {}
        head = fix_head(obj, self.c, card)
        if not head["title"]:
            head["title"] = self._card_head(card)["title"]
        vs = validate_head(head, self.c)
        todo = [v for v in vs if v.code in LEAN_SAFETY]
        if todo:
            fixed = self._repair(head, todo, job)
            if fixed is not None:
                new = fix_head(fixed, self.c, card)
                new["title"] = new["title"] or head["title"]
                vs2 = validate_head(new, self.c)
                if _safer(vs2, vs):
                    head, vs = new, vs2
        if hard(vs):
            head = drop_head_parts(head, self.c, card)
            head["title"] = head["title"] or self._card_head(card)["title"]
            vs = validate_head(head, self.c)
        if vs:
            self.log({"event": "head", "codes": codes(vs)})
        return head

    def _show_head(self, job: _Job, head: dict) -> None:
        """The head as a title and a world event (book_ops.head_lines), applied like a mirror applies them; chapter 1's
        plan is made again now that the bible has a hero."""
        era = str((job.card or {}).get("era") or "any")
        for kind, data in zip(("title", "world"), ops.head_lines(head, era)):
            event = Event(kind, "n", data)
            ops.apply_event(self.c, job.book, event)
            job.emit(event)
        job.plan = plan_chapter(self.c, job.book, 1)

    # ------------------------------------------------------------ chapters
    def _brief(self, plan: ChapterPlan, book: Book) -> str:
        return ""                                   # no director brief: the request is the prototype's

    def _end_chapter(self, job: _Job, locked: Callable[[], int]) -> None:
        return None                                 # no structural check and no rewrite: never a truncate

    def _label(self, job: _Job) -> str:
        """A child's idea in the child's own words, when they may be quoted (freetext.quotable)."""
        opt = job.plan.chosen if job.plan is not None else None
        return ft.quotable(self.c, opt.label) if opt is not None and opt.kind == "idea" and opt.label else ""

    def _chapter_messages(self, job: _Job, note: str) -> list[dict]:
        return P.lean_messages(self.c, job.book, job.node, job.plan, label=self._label(job), note=note)

    def _repair_messages(self, obj: dict, vs: list[Violation], job: _Job) -> list[dict]:
        return P.lean_repair_messages(self.c, job.book, job.node, obj, vs, card=job.card)

    def _repeat_pages(self, job: _Job) -> list:
        """The book so far is in every lean request: a page that copies one of this world line's is a repeat — but for
        the finale's last page, the book's first page is left out: LEAN_STORY asks 「结尾呼应第一页」 (r1 001's last page
        copied page-1 lines), and a last page that brought one of them back was skipped in every reply until the finale
        failed (M3 r3 review, R3-ROB-4). validate's echo.copy still flags two copied lines."""
        node, plan = job.node, job.plan
        pages = list(self._prior_pages(job.book, node)) + list(node.pages)
        root = job.book.nodes.get("n")
        if plan is not None and plan.is_final and ops.planned(node.pages) + 1 == len(plan.pages) and root is not None:
            first = {p.id for p in root.pages[:ops.start_of(root.pages, 1)]}
            pages = [p for p in pages if p.id not in first]
        return pages

    def _shaped(self, obj: dict, node_id: str) -> dict | None:
        """A line whose type is not page, choice or end, read by its shape (M3 r3 review, R3-ROB-9: P1 typed 「Page」 and
        the fork 「choices」 were dropped and the stream read on into the next chapter): a lines list makes it a page, an
        opts list a fork (type_fixed). One with lines or opts of another shape cannot be read: None, and the stream
        stops there. Any other line comes back as it is (a plan or head line, dropped while the stream goes on)."""
        t = obj.get("type")
        if t in ("page", "choice", "end") + HEAD_TYPES:             # a head or plan line stays what it says it is
            return obj
        for key, kind in (("lines", "page"), ("opts", "choice")):
            if isinstance(obj.get(key), list):
                self.log({"event": "type_fixed", "node": node_id, "type": str(t)[:20], "as": kind})
                return dict(obj, type=kind)
        if "lines" in obj or "opts" in obj:
            self.log({"event": "line_dropped", "node": node_id, "type": str(t)[:20], "stop": True})
            return None
        return obj

    def _chapter_obj(self, obj, job: _Job) -> bool:
        """Pages, the fork and the end line as the classic writer settles them (lean checks; the stream is cut after
        the fork or the end line), an odd type read by its shape (_shaped); a plan line, a head line again and any other
        type are dropped."""
        if isinstance(obj, dict) and "__parse_error__" not in obj:
            obj = self._shaped(obj, job.node.id)
            if obj is None:
                return False
            t = obj.get("type")
            if t not in ("page", "choice", "end"):
                self.log({"event": "line_dropped", "node": job.node.id, "type": str(t)[:20]})
                return True
            if t == "end" and job.plan.is_final and job.node.ending is None and obj.get("family") != job.node.family:
                self.log({"event": "end_family", "node": job.node.id, "model": obj.get("family"),
                          "family": job.node.family})
        return super()._chapter_obj(obj, job)

    def _tail(self, job: _Job, note: str, model) -> LLMError | None:
        """The fork (or the end line) alone once every page exists: the same request saying so, streamed and cut after
        the wanted line; other lines of the reply are dropped."""
        want = "end" if job.plan.is_final else "choice"
        msgs = P.lean_messages(self.c, job.book, job.node, job.plan, label=self._label(job), note=note, tail=True)

        def handle(obj) -> bool:
            if isinstance(obj, dict) and "__parse_error__" not in obj:
                obj = self._shaped(obj, job.node.id)
                if obj is None:
                    return False
            if isinstance(obj, dict) and obj.get("type") == want:
                return self._chapter_obj(obj, job)
            self.log({"event": "line_dropped", "node": job.node.id, "tail": True,
                      "type": str(obj.get("type"))[:20] if isinstance(obj, dict) else "unreadable"})
            return True

        err = self._stream("chapter", msgs, handle, job.cancel, model=model)
        if not self._complete(job.node, job.plan):
            self.log({"event": "tail_missing", "node": job.node.id, "want": want})
        return err

    # ------------------------------------------------------------ settling lines (validate.py's lean profile)
    def _settle_page(self, obj: dict, ctx: PageCtx, job: _Job):
        """lean_check_page (every code fix, the cameos), then one repair for a safety hit, taken only if safer; a hard
        problem left drops the page. Fixes, residual codes and cameos go into _meta."""
        page, vs, fixes, cameos = lean_check_page(obj, ctx, MECHANICAL)
        repaired = False
        todo = [v for v in vs if v.code in LEAN_SAFETY]
        if todo and isinstance(page, dict):
            fixed = self._repair(page, todo, job)
            if fixed is not None:
                new = lean_check_page(fixed, ctx, MECHANICAL)
                if _safer(new[1], vs):
                    (page, vs, fixes, cameos), repaired = new, True
        if hard(vs) or not isinstance(page, dict):
            job.unsafe = job.unsafe or any(v.code in LEAN_SAFETY for v in vs)       # the next request says SAFER
            return None, vs
        page["_meta"] = {"repaired": repaired, "fixes": fixes, "residual": codes(vs), "cameos": cameos}
        return page, vs

    def _settle_choice(self, obj: dict, fctx: ForkCtx, job: _Job):
        """soft_fix_choice (strings, ids, kinds, script, the fixed replacements, the question mark), one repair for a
        safety hit or a grave problem (hard, or a q or option text the child could not be shown: _unshown), taken only if
        safer, last_question; a grave problem left drops the fork (the fork-only request asks again). Its other codes are
        logged, never repaired."""
        obj = soft_fix_choice(obj, self.c)
        vs = validate_choice(obj, fctx)
        grave = _grave(vs)
        todo = [v for v in vs if v.code in LEAN_SAFETY or v in grave]
        if todo:
            fixed = self._repair(obj, todo, job)
            if fixed is not None:
                new = soft_fix_choice(fixed, self.c)
                vs2 = validate_choice(new, fctx)
                if _safer(vs2, vs):
                    obj, vs = new, vs2
        if "fork.q_ask" in codes(vs):
            obj = last_question(obj)
            vs = validate_choice(obj, fctx)
        if vs:
            self.log({"event": "fork_codes", "node": job.node.id, "codes": codes(vs)})
        if _grave(vs):
            job.unsafe = job.unsafe or any(v.code in LEAN_SAFETY for v in vs)       # the next request says SAFER
            return None, vs
        return obj, vs
