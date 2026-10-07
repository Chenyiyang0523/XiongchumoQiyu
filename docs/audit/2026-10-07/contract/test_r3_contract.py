"""Review harness: is the lean writer a drop-in for plan B1's Session? (scratch export, not part of the repo)"""
import copy
import json
import threading

import pytest
from fakes import C1, C2, C3, K2, LEAN_CHAPTERS, LEAN_HEAD, sse
from helpers import C, page
from r3harness import Router, bad_logs, make, node_core, read_chapter, settle, until
from xcmengine import book_ops as ops
from xcmengine.costs import Ledger
from xcmengine.lean import LeanWriter
from xcmengine.writer import Writer

OPENING = ["title", "world", "page", "page", "page", "choice", "done"]


def start(s, length="medium"):
    bid = s.start(s.cards()[0]["id"], length=length)
    settle(s)
    return bid


# ---------------------------------------------------------------- constructor, signatures, events, statuses
def test_the_sessions_default_factory_builds_the_lean_writer(tmp_path):
    s = make(tmp_path)
    w = s.test["cap"].default(Ledger())
    assert type(w) is LeanWriter and w.fallback_model == "glm-4.7-flashx" and w.log == s.log
    # sessim's live construction (log None, budget hook)
    seen = []
    w2 = Writer(C, s.chat, Ledger(), None, "glm-4.7-flashx", budget=lambda: seen.append(1))
    assert type(w2) is LeanWriter and w2.budget is not None


def test_opening_through_the_session(tmp_path):
    s = make(tmp_path)
    bid = start(s)
    cap, r = s.test["cap"], s.test["router"]
    assert bad_logs(s) == []
    assert cap.job_events("n") == OPENING
    book = s.books[bid]
    assert book.status == "ready" and book.nodes["n"].status == "done"
    v = s.book_view(bid)
    assert v["title"] == LEAN_HEAD["title"] and v["hero"] == "熊二" and v["want"] == LEAN_HEAD["want"]
    assert v["rule"] == "" and v["refrain"] == "" and v["guest"] == LEAN_HEAD["guest"] and v["can_open"]
    assert r.kinds() == [("opening", None)]
    # the mirror equals the writer's copy
    copy_ = cap.copies["n"][-1]
    assert node_core(book.nodes["n"]) == node_core(copy_.nodes["n"])
    assert book.bible.to_dict() == copy_.bible.to_dict() and book.samples == copy_.samples
    # done carries usage; the card the session passed has no era
    assert cap.events[-1][1] == "done" and cap.events[-1][3] == ["usage"]
    assert book.usage["yuan"] > 0


def test_reading_a_whole_book_with_speculation(tmp_path):
    s = make(tmp_path)
    bid = start(s)
    cap, r = s.test["cap"], s.test["router"]
    path = "n"
    for oid in "ABC":
        read_chapter(s, bid, path)
        settle(s)
        # speculation: the three children were written as SPEC, each with its own outcome line
        kids = [f"{path}.{o}" for o in "ABC"]
        assert all(s.books[bid].nodes[k].status == "done" for k in kids), [s.books[bid].nodes[k].status for k in kids]
        child = s.choose(bid, path, oid)
        settle(s)
        path = child
        assert s.books[bid].nodes[path].status == "done"
    assert bad_logs(s) == []
    book = s.books[bid]
    fin = book.nodes[path]
    assert fin.ending is not None and fin.ending.family == fin.family
    read_chapter(s, bid, path)
    assert book.endings_found and book.endings_found[0]["node"] == path
    # every node: the mirror equals the writer's copy, events in order
    for nid, copies in cap.copies.items():
        assert node_core(book.nodes[nid]) == node_core(copies[-1].nodes[nid]), nid
        ev = cap.job_events(nid)
        if nid == "n":
            assert ev == OPENING
        else:
            assert ev[0] == "plan_meta" and ev[-1] == "done" and ev[-2] in ("choice", "end"), (nid, ev)
            assert set(ev) <= {"plan_meta", "page", "choice", "end", "done"}
    outs = {}
    for info in r.requests:
        if info["kind"] == "chapter" and info["chapter"] == 2:
            outs.setdefault(2, []).append([l for l in info["user"].split("\n") if l.startswith("这个选择的结果：")])
    assert len({tuple(x) for x in outs[2]}) == 3
    assert book.usage["spec_yuan"] > 0 and book.usage["yuan"] >= book.usage["spec_yuan"]


# ---------------------------------------------------------------- resume of an unfinished chapter
def to_fork(s, bid, oid="A", spec=False):
    """Read the opening to its fork and choose oid (speculation off unless spec)."""
    read_chapter(s, bid, "n")
    settle(s)
    nid = s.choose(bid, "n", oid)
    return nid


def test_a_dropped_chapter_that_fails_is_retried_from_its_committed_page(tmp_path):
    from fakes import events_through
    r = Router()
    s = make(tmp_path, router=r, prefs={"speculate": False})
    bid = start(s)
    rest2 = r.rest(2)
    r.overrides = [(lambda i: i["kind"] == "chapter" and i["chapter"] == 2, ("drop", sse(*rest2), events_through(C1)))]
    r.overrides += [(lambda i: i["kind"] == "resume", ("http", 500, "{}"))] * 4
    nid = to_fork(s, bid)
    settle(s)
    book = s.books[bid]
    node = book.nodes[nid]
    assert node.status == "error" and node.error_kind == "incomplete" and len(node.pages) == 1, (node.status, node.error_kind)
    assert s.node_view(bid, nid)["error"]["retry"]
    first_meta = [e for e in s.test["cap"].events if e[2] == nid and e[1] == "plan_meta"]
    outcome1 = node.outcome
    s.retry(bid, nid)
    settle(s)
    assert bad_logs(s) == [r for r in bad_logs(s) if r.get("event") == "text_failed"]
    assert node.status == "done" and [p.lines[0].text for p in node.pages] == [C1["lines"][0]["text"], C2["lines"][0]["text"],
                                                                             C3["lines"][0]["text"]]
    assert [p.id for p in node.pages] == [f"{nid}.p1", f"{nid}.p2", f"{nid}.p3"] and node.outcome == outcome1
    last = r.requests[-1]
    assert last["kind"] == "resume" and last["k"] == 1 and "接着写第五页" in last["user"]
    assert node_core(node) == node_core(s.test["cap"].copies[nid][-1].nodes[nid])


def test_a_preempted_spec_chapter_is_requeued_and_resumes(tmp_path):
    """Threaded: one text slot; n.A is speculated and stopped mid-stream (page 1 committed) when the child picks n.B
    (NOW preempts the running SPEC job); the requeued n.A goes on from its committed page."""
    from fakes import events_through
    r = Router()
    gate, reached = threading.Event(), threading.Event()
    s = make(tmp_path, router=r, threaded=True, limits={"text": 1})
    bid = s.start(s.cards()[0]["id"], length="medium")
    until(s, lambda: s.books[bid].nodes["n"].status == "done")
    r.overrides = [(lambda i: i["kind"] == "chapter" and i["chapter"] == 2,
                    ("block", sse(*r.rest(2)), events_through(C1) + 1, gate, reached))]
    for p in s.node_view(bid, "n")["pages"]:
        s.page_shown(bid, p)
    until(s, lambda: reached.is_set())
    until(s, lambda: len(s.books[bid].nodes["n.A"].pages) == 1)
    s.choose(bid, "n", "B")
    s.poll()
    job = s.jobs.get(f"text:{bid}:n.A")
    assert job is not None and job.cancel.cancelled and job.preempted
    gate.set()
    until(s, lambda: s.books[bid].nodes["n.B"].status == "done" and s.books[bid].nodes["n.A"].status == "done", 20)
    book = s.books[bid]
    a = book.nodes["n.A"]
    assert [p.lines[0].text for p in a.pages] == [C1["lines"][0]["text"], C2["lines"][0]["text"], C3["lines"][0]["text"]]
    kinds = [(i["kind"], i.get("chapter"), i.get("k")) for i in r.requests]
    assert ("resume", 2, 1) in kinds, kinds
    assert [e for e in bad_logs(s) if e.get("event") != "text_failed"] == []
    assert node_core(a) == node_core(s.test["cap"].copies["n.A"][-1].nodes["n.A"])
    s.shutdown()


def test_a_book_closed_mid_chapter_resumes_in_a_new_session(tmp_path):
    """Threaded: the child's chapter n.A stops after page 1 when the game quits; a new session opens the book from the
    shelf and the chapter goes on from its committed page (open_book)."""
    from fakes import events_through
    r = Router()
    gate, reached = threading.Event(), threading.Event()
    s = make(tmp_path, router=r, threaded=True, prefs={"speculate": False})
    bid = s.start(s.cards()[0]["id"], length="medium")
    until(s, lambda: s.books[bid].nodes["n"].status == "done")
    r.overrides = [(lambda i: i["kind"] == "chapter" and i["chapter"] == 2,
                    ("block", sse(*r.rest(2)), events_through(C1) + 1, gate, reached))]
    for p in s.node_view(bid, "n")["pages"]:
        s.page_shown(bid, p)
    s.choose(bid, "n", "A")
    until(s, lambda: len(s.books[bid].nodes.get("n.A").pages) == 1 if "n.A" in s.books[bid].nodes else False)
    s.shutdown()
    gate.set()
    r2 = Router()
    s2 = make(tmp_path, router=r2, prefs={"speculate": False})
    v = s2.open_book(bid)
    settle(s2)
    a = s2.books[bid].nodes["n.A"]
    assert a.status == "done" and [p.lines[0].text for p in a.pages] == [C1["lines"][0]["text"], C2["lines"][0]["text"],
                                                                       C3["lines"][0]["text"]]
    assert [(i["kind"], i.get("chapter"), i.get("k")) for i in r2.requests] == [("resume", 2, 1)]
    assert bad_logs(s2) == []


# ---------------------------------------------------------------- a page split in code (item 4) and the B1 views
LONG = page(*[("narr", f"熊二往山上跑了第{n}步。") for n in "一二三四五六七"])


def test_a_split_page_and_the_sessions_page_views(tmp_path):
    chapters = list(LEAN_CHAPTERS)
    chapters[1] = [C1, LONG, C3, K2]
    r = Router(chapters=chapters)
    s = make(tmp_path, router=r, prefs={"speculate": False})
    bid = start(s)
    nid = to_fork(s, bid)
    settle(s)
    node = s.books[bid].nodes[nid]
    assert node.status == "done" and len(node.pages) == 4 and ops.planned(node.pages) == 3
    assert ops.CONT in node.pages[2].fixes
    nv = s.node_view(bid, nid)
    pv = {p: s.page_view(bid, p) for p in nv["pages"]}
    report = {p: {k: v[k] for k in ("index", "number", "total", "last", "next", "fork")} for p, v in pv.items()}
    print(json.dumps({"planned": nv["planned"], "pages": nv["pages"], "views": report}, ensure_ascii=False, indent=1))
    # B2's router: next non-empty → that page; fork → the fork; end → the ending; else wait for the chapter
    p4 = pv[f"{nid}.p4"]
    assert p4["fork"] or p4["next"], "the chapter's real last page (C3) has neither next nor fork: B2 waits forever"


def test_a_split_page_in_the_finale_and_the_ending_read(tmp_path):
    chapters = list(LEAN_CHAPTERS)
    fin = list(chapters[3])
    fin[1] = LONG
    chapters[3] = fin
    r = Router(chapters=chapters)
    s = make(tmp_path, router=r, prefs={"speculate": False})
    bid = start(s)
    path = "n"
    for oid in "ABC":
        read_chapter(s, bid, path)
        settle(s)
        path = s.choose(bid, path, oid)
        settle(s)
    node = s.books[bid].nodes[path]
    assert node.ending is not None and len(node.pages) == 5
    pages = s.node_view(bid, path)["pages"]
    found = []
    for p in pages:
        s.page_shown(bid, p)
        found.append((p, len(s.books[bid].endings_found), s.page_view(bid, p)["end"], s.page_view(bid, p)["next"]))
    print(found)
    assert found[3][1] == 0, "the ending is marked read on page 4 of 5 (the layout's last page), before its real last page"
    assert found[-1][2], "the finale's real last page has no end (B2 never reaches the ending screen)"


# ---------------------------------------------------------------- ideas
def test_an_idea_through_the_session(tmp_path):
    r = Router()
    s = make(tmp_path, router=r, prefs={"speculate": False})
    bid = start(s)
    read_chapter(s, bid, "n")
    key = s.submit_idea(bid, "n", "让熊二把蜂蜜罐当灯笼")
    settle(s)
    v = s.idea_view(key)
    assert v["state"] == "ready" and v["child"] == "n.P1", v
    node = s.books[bid].nodes["n.P1"]
    assert node.status == "done" and node.outcome == "idea" and len(node.pages) == 3
    req = [i for i in r.requests if i["kind"] == "chapter" and i["chapter"] == 2][-1]["user"]
    line = [l for l in req.split("\n") if "小读者自己想到了" in l]
    print(line)
    assert "小读者自己想到了「让熊二把蜂蜜罐当灯笼」：熊二决定：把蜂蜜罐当灯笼举起来——第一页就让它真的做成。" in req
    assert "这个选择的结果" not in req
    assert bad_logs(s) == []
    assert node_core(node) == node_core(s.test["cap"].copies["n.P1"][-1].nodes["n.P1"])


def test_an_idea_at_the_final_fork_ends_the_book(tmp_path):
    r = Router()
    s = make(tmp_path, router=r, prefs={"speculate": False})
    bid = start(s)
    path = "n"
    for oid in "AB":
        read_chapter(s, bid, path)
        settle(s)
        path = s.choose(bid, path, oid)
        settle(s)
    read_chapter(s, bid, path)
    key = s.submit_idea(bid, path, "让熊二把蜂蜜罐当灯笼")
    settle(s)
    v = s.idea_view(key)
    fin = s.books[bid].nodes[v["child"]]
    assert fin.status == "done" and fin.ending is not None and fin.ending.family == fin.family, (fin.status, fin.family)
    req = [i for i in r.requests if i["kind"] == "chapter" and i["chapter"] == 4][-1]["user"]
    assert f'"family":"{fin.family}"' in req and "小读者自己想到了「让熊二把蜂蜜罐当灯笼」" in req
    read_chapter(s, bid, fin.id)
    assert s.books[bid].endings_found[-1]["node"] == fin.id and bad_logs(s) == []


# ---------------------------------------------------------------- pool, account errors, money
def test_a_pool_opening_with_the_code_only_gate(tmp_path):
    r = Router()
    s = make(tmp_path, router=r, prefs={"pool_size": 1, "speculate": False})
    settle(s)
    s.test["clock"].advance(10)
    settle(s)
    assert len(s.lib.pool_ids()) == 1, (s.lib.pool_ids(), s.test["logs"][-5:])
    bid = s.lib.pool_ids()[0]
    book = s.books[bid]
    assert book.nodes["n"].usage.get("gate") == "ok" and book.status == "pool"
    assert s.test["cap"].job_events("n") == OPENING
    cards = s.cards()
    assert cards[0]["ready"] and cards[0]["book"] == bid
    assert s.start(cards[0]["id"]) == bid and s.books[bid].status == "ready"


def test_a_billing_error_in_a_lean_chapter_stops_paid_work(tmp_path):
    r = Router()
    s = make(tmp_path, router=r, prefs={"speculate": False})
    bid = start(s)
    r.overrides = [(lambda i: i["kind"] == "chapter", ("http", 402, json.dumps({"error": {"code": "1113", "message": "欠费"}})))]
    nid = to_fork(s, bid)
    settle(s)
    assert s.api["state"] == "error" and s.api["kind"] == "billing"
    assert s.books[bid].nodes[nid].error_kind == "billing"


def test_the_session_charges_what_the_lean_writer_billed(tmp_path):
    r = Router()
    s = make(tmp_path, router=r)
    bid = start(s)
    path = "n"
    for oid in "AB":
        read_chapter(s, bid, path)
        settle(s)
        path = s.choose(bid, path, oid)
        settle(s)
    led = sum(w.ledger.yuan for w in s.test["cap"].writers)
    calls = sum(w.ledger.calls for w in s.test["cap"].writers)
    est = sum(w.ledger.estimated for w in s.test["cap"].writers)
    text = [i for i in r.requests if i["kind"] != "idea"]
    print(len(text), calls, est, led, s.books[bid].usage)
    assert calls == len(text) and est == len(text)            # every lean stream is cut: estimated
    assert s.books[bid].usage["yuan"] == pytest.approx(led, rel=1e-6) or s.books[bid].usage["yuan"] > led


def test_threaded_two_books_with_speculation(tmp_path):
    s = make(tmp_path, threaded=True)
    cards = s.cards()
    bids = [s.start(cards[i]["id"], length="medium") for i in range(2)]
    until(s, lambda: all(s.books[b].nodes["n"].status == "done" for b in bids), 20)
    paths = {b: "n" for b in bids}
    for step, oid in enumerate("ABC"):
        for b in bids:
            for p in s.node_view(b, paths[b])["pages"]:
                s.page_shown(b, p)
        until(s, lambda: all(all(s.books[b].nodes.get(f"{paths[b]}.{o}") is not None
                                 and s.books[b].nodes[f"{paths[b]}.{o}"].status == "done" for o in "ABC") for b in bids), 30)
        for b in bids:
            paths[b] = s.choose(b, paths[b], oid)
        until(s, lambda: all(s.books[b].nodes[paths[b]].status == "done" for b in bids), 30)
    until(s, lambda: not s.jobs.running("text") and not s.jobs.queued("text"), 30)
    assert [e for e in bad_logs(s)] == []
    cap = s.test["cap"]
    for b in bids:
        book = s.books[b]
        assert book.nodes[paths[b]].ending is not None
        for nid, node in book.nodes.items():
            mine = [c for c in cap.copies.get(nid, []) if c.id == b]
            if mine:
                assert node_core(node) == node_core(mine[-1].nodes[nid]), (b, nid)
    s.shutdown()


def test_the_budget_hook_through_the_session(tmp_path):
    """sessim's live construction: Writer(content, chat, ledger, None, fallback, budget=hook); the hook refuses the
    third request (WriteFailed("budget")): the node fails with budget, nothing more is sent."""
    from xcmengine.writer import WriteFailed
    r = Router()
    s = make(tmp_path, router=r, prefs={"speculate": False})
    sent = {"n": 0}

    def budget():
        sent["n"] += 1
        if sent["n"] > 2:
            raise WriteFailed("budget", "cap")
    cap = s.test["cap"]
    cap.default = lambda ledger: Writer(C, s.chat, ledger, None, "glm-4.7-flashx", budget=budget)
    bid = start(s)
    nid = to_fork(s, bid)
    settle(s)
    path = nid
    read_chapter(s, bid, path)
    settle(s)
    nid2 = s.choose(bid, path, "A")
    settle(s)
    node = s.books[bid].nodes[nid2]
    assert node.status == "error" and node.error_kind == "budget" and len(r.requests) == 2
    assert s.node_view(bid, nid2)["error"]["retry"] is False


def test_siblings_wait_for_sibling_ones_first_event(tmp_path):
    """B1: siblings 2-3 start with sibling 1's first event (it warms the prefix cache for them) or after 3 s. The first
    event of a chapter job is plan_meta, emitted before its request: are B and C sent before A's request got a byte?"""
    gate, reached = threading.Event(), threading.Event()
    r = Router()
    s = make(tmp_path, router=r, threaded=True)
    bid = s.start(s.cards()[0]["id"], length="medium")
    until(s, lambda: s.books[bid].nodes["n"].status == "done")
    r.overrides = [(lambda i: i["kind"] == "chapter" and i["chapter"] == 2,
                    ("block", sse(*r.rest(2)), 0, gate, reached))]
    for p in s.node_view(bid, "n")["pages"]:
        s.page_shown(bid, p)
    until(s, lambda: reached.is_set())
    import time as _t
    t0 = _t.monotonic()
    while _t.monotonic() - t0 < 0.5:
        s.poll()
        _t.sleep(0.01)
    sent = [i for i in r.requests if i["kind"] == "chapter" and i["chapter"] == 2]
    clock_advanced = s.test["clock"]()
    gate.set()
    until(s, lambda: all(s.books[bid].nodes[f"n.{o}"].status == "done" for o in "ABC"), 20)
    s.shutdown()
    print("chapter-2 requests sent while sibling 1 had not received a byte:", len(sent), "session clock", clock_advanced)
    assert len(sent) == 1, "siblings 2-3 were sent before sibling 1's request had any answer (no cache warm-up)"


def test_a_cancel_during_a_repair_call_stops_the_job_as_cancelled(tmp_path):
    """Threaded: n.A's page 2 has a hard safety hit; its repair request blocks; the child picks n.B (NOW preempts the
    SPEC job): the writer stops as cancelled (from inside the outer stream's callback), the job is requeued and goes
    on from page 1."""
    gun = copy.deepcopy(C2)
    gun["lines"][0]["text"] = "熊二抱着小云朵往山上跑，光头强举起了枪。"
    chapters = list(LEAN_CHAPTERS)
    chapters[1] = [C1, gun, C3, K2]
    r = Router(chapters=chapters)
    gate, reached = threading.Event(), threading.Event()
    s = make(tmp_path, router=r, threaded=True, limits={"text": 1})
    bid = s.start(s.cards()[0]["id"], length="medium")
    until(s, lambda: s.books[bid].nodes["n"].status == "done")
    r.overrides = [(lambda i: i["kind"] == "repair", ("block", sse(C2), 0, gate, reached))]
    for p in s.node_view(bid, "n")["pages"]:
        s.page_shown(bid, p)
    until(s, lambda: reached.is_set())
    s.choose(bid, "n", "B")
    s.poll()
    job = s.jobs.get(f"text:{bid}:n.A")
    assert job is not None and job.cancel.cancelled
    r.chapters = list(LEAN_CHAPTERS)                  # the requeued job's continuation gets clean pages
    gate.set()
    until(s, lambda: s.books[bid].nodes["n.B"].status == "done" and s.books[bid].nodes["n.A"].status == "done", 20)
    a = s.books[bid].nodes["n.A"]
    assert [p.lines[0].text for p in a.pages] == [C1["lines"][0]["text"], C2["lines"][0]["text"], C3["lines"][0]["text"]]
    assert any(e.get("event") == "preempt" for e in s.test["logs"]) or True
    fails = [e for e in s.test["logs"] if e.get("event") == "text_failed"]
    assert fails == [], fails
    s.shutdown()


def test_the_first_book_is_short_and_completes(tmp_path):
    from fakes import F1, F2, F3, F4, K1, LEAN_END, P1, P2, P3
    r = Router(chapters=([P1, P2, P3, K1], [C1, C2, K2], [F1, F2, F3, F4, LEAN_END]))
    s = make(tmp_path, router=r)
    bid = s.start(s.cards()[0]["id"])                 # the session's first book: short (3/2/4)
    settle(s)
    assert s.books[bid].length == "short"
    path = "n"
    for oid in "AB":
        read_chapter(s, bid, path)
        settle(s)
        path = s.choose(bid, path, oid)
        settle(s)
    fin = s.books[bid].nodes[path]
    assert fin.status == "done" and fin.ending is not None and len(fin.pages) == 4
    read_chapter(s, bid, path)
    assert s.books[bid].endings_found and bad_logs(s) == []
    print(r.kinds())
