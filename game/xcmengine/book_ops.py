"""Pure operations that create books and apply validated model lines to them (no I/O, no network).

Status is the caller's business: apply_end and the "end" event never mark a node done (the writer reports a finished
job with a "done" event). book.endings_found lists the endings the child has READ (mark_ending_read), not every
ending written ahead. Model lists may arrive as a single string ("items_add": "小铃铛"); they are read with as_list.
"""
from __future__ import annotations

import hashlib
import re

from . import textutil as tu
from .content import Content
from .models import (ArtBrief, BiblePublic, BibleSecret, Book, ChoicePoint, Ending, LedgerItem, Line, Node, Option, Page,
                     StoryState, child_id, page_id)
from .seeds import new_rng, pick_exemplars, pick_samples
from .validate import (DECISION, ForkCtx, PageCtx, action_token, as_list, check_strings, clue_shown, count_fork_usage,
                       count_usage, first_str, fix_world, resolve_id, swap_words, thing_name)

QUALITY = {"careful": "care", "bold": "brave", "silly": "fun", "idea": "wit"}
CONT = "len.cont"               # page.fixes mark of the second half of a page split in code (M3 r2, findings #15)
TWIST_BAND = (0.15, 0.75)       # usable twist typicality: neither the obvious twist nor a far-fetched one (spec §5)
MAX_TWISTS = 3                  # one per fork-1 branch
_PAREN = re.compile(r"[（(][^）)]*[）)]")


def _dict(x) -> dict:
    return dict(x) if isinstance(x, dict) else {}


def item_core(name) -> str:
    """An item name without its parenthesised remarks: 小铃铛（坏了的） → 小铃铛."""
    return _PAREN.sub("", str(name or "")).strip()


def new_book(content: Content, card: dict, length: str, seed: str, now: float = 0.0) -> Book:
    rng = new_rng(seed)
    book = Book(id="b" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10], length=length,
                premise={"card": card.get("id", ""), "title": card.get("title", ""), "hook": card.get("hook", ""),
                         "twist_hint": card.get("twist_hint", ""), "cast": list(card.get("cast", [])),
                         "custom": bool(card.get("custom", False))},
                seeds=dict(card.get("dims") or {}), created=now, updated=now)
    avoid = [w for w in card.get("avoid") or [] if isinstance(w, str) and w]
    if avoid:                   # what the card heard the last books used: every lean request shows the same card
        book.premise["avoid"] = avoid
    book.samples = pick_samples(content, card.get("cast", []), rng)
    book.exemplars = pick_exemplars(content, rng)
    book.nodes["n"] = Node(id="n", parent=None, via=None, chapter=1, role=content.layout(length)[0][1])
    return book


def apply_title(book: Book, obj: dict) -> None:
    book.bible = book.bible or BiblePublic()
    book.bible.title = str(obj.get("title", "")).strip()
    book.bible.logline = str(obj.get("logline", "")).strip()


def apply_world(book: Book, obj: dict, content: Content) -> None:
    book.bible = book.bible or BiblePublic()
    b = book.bible
    b.hero = str(obj.get("hero") or "")
    b.cast = [c for c in as_list(obj.get("cast")) if isinstance(c, str)]
    era = obj.get("era")
    b.era = era if isinstance(era, str) and era in content.eras else "any"
    b.want, b.oddity = str(obj.get("want", "")), str(obj.get("oddity", ""))
    b.rule = _dict(obj.get("rule"))
    b.guest = _dict(obj.get("guest"))
    b.antagonist = _dict(fix_world(obj, content).get("antagonist"))      # one id, also on the mirror path
    b.places = [str(p) for p in as_list(obj.get("places")) if p][:3]
    b.refrain = str(obj.get("refrain", ""))
    book.samples = pick_samples(content, b.cast, new_rng(book.id + "|samples"))


def head_lines(head: dict, era: str = "any") -> tuple[dict, dict]:
    """The lean writer's extended title line (M3 r3 item 2, after validate.fix_head) as the two head lines a mirror
    applies: a title line (title, logline) and a world line with the minimal bible — hero, cast, guest {name, look},
    places and want, with the card's era. No oddity, rule, refrain or antagonist, and no setups or secret: none are
    asked for. The writer applies both through apply_event, so its book and the session's mirror agree (apply_world
    also picks the cast's voice samples)."""
    g = head.get("guest") if isinstance(head.get("guest"), dict) else {}
    title = {"type": "title", "title": str(head.get("title") or ""), "logline": str(head.get("logline") or "")}
    world = {"type": "world", "hero": str(head.get("hero") or ""),
             "cast": [c for c in as_list(head.get("cast")) if isinstance(c, str)], "era": era,
             "want": str(head.get("want") or ""),
             "guest": {"name": str(g.get("name") or ""), "look": str(g.get("look") or "")},
             "places": [str(p) for p in as_list(head.get("places")) if p][:3]}
    return title, world


def join_cast(content: Content, book: Book, node: Node, cids) -> list[str]:
    """Canon characters a lean page brought onto this world line (validate.lean_fix_page's cameos, M3 r3 item 4) join
    node.state.cast_extra, which its children inherit; bible.cast never changes. Returns those that joined."""
    cast = book.bible.cast if book.bible else []
    joined = []
    for cid in cids or ():
        if cid in content.characters and cid not in cast and cid not in node.state.cast_extra:
            node.state.cast_extra.append(cid)
            joined.append(cid)
    return joined


def _setup(item: dict) -> dict:
    """A setup with string id (stripped), what and role: a model may write "id": 1 and a page "plant": ["1"], so
    bible.setups and every root ledger built from it (apply_setups, truncate) must agree."""
    s = {k: "" if item.get(k) is None else str(item.get(k)) for k in ("id", "what", "role")}
    return dict(item, id=s["id"].strip(), what=s["what"], role=s["role"])


def _setup_ledger(book: Book) -> list[LedgerItem]:
    """The root's ledger: one planned item per bible setup (also for a bible saved before the ids were strings)."""
    return [LedgerItem(id=s["id"], kind="setup", what=s["what"], role=s["role"])
            for s in map(_setup, book.bible.setups if book.bible else [])]


def apply_setups(book: Book, obj: dict) -> None:
    """Setups are frozen once the opening has pages (the pages plant them); ids, whats and roles are stored as
    strings."""
    root = book.nodes["n"]
    if root.pages:
        raise ValueError("setups are frozen once the opening has pages")
    book.bible = book.bible or BiblePublic()
    book.bible.setups = [_setup(i) for i in as_list(obj.get("items")) if isinstance(i, dict)]
    root.ledger = _setup_ledger(book)


def _usable_twists(book: Book, raw) -> list[dict]:
    """idea, setup and clue given, the setup one of this book's, typicality inside TWIST_BAND — except the card's own
    truth (marked `card` by mark_card_twist): it is curated, neither the obvious twist nor a far-fetched one."""
    ids = {s.get("id") for s in (book.bible.setups if book.bible else [])}
    lo, hi = TWIST_BAND
    out = []
    for t in as_list(raw):
        if not isinstance(t, dict) or not all(isinstance(t.get(k), str) and t[k].strip()
                                              for k in ("idea", "setup", "clue")):
            continue
        typ = t.get("typicality")
        banded = not isinstance(typ, bool) and isinstance(typ, (int, float)) and lo <= typ <= hi
        if not (banded or t.get("card") is True) or t["setup"] not in ids:
            continue
        out.append(dict(t))
    return out[:MAX_TWISTS]


def mark_card_twist(content: Content, book: Book, obj: dict) -> dict:
    """The secret line with its first twist marked `"card": True` when it retells the card's truth (premise twist_hint):
    two content bigrams in common, every character name, the guest and the places taken out. The bible asks for the
    card's truth first (M3 r2 findings #5 fix 4: 4 of 5 r1 books replaced it with adult ones of their own). Pure; the
    writer marks the line before apply_secret, and the event carries the mark, so a mirror binds the same way."""
    twists = obj.get("twists") if isinstance(obj, dict) else None
    hint = str(book.premise.get("twist_hint") or "")
    first = twists[0] if isinstance(twists, list) and twists else None
    if not isinstance(first, dict) or not isinstance(first.get("idea"), str) or not hint.strip():
        return obj
    b = book.bible
    names = [n for cid in list(content.characters) + list(content.minor) for n in content.names(cid)]
    if b is not None:
        names += [p for p in b.places if isinstance(p, str)] if isinstance(b.places, list) else []
        names += [b.guest["name"]] if b.has_guest() and isinstance(b.guest.get("name"), str) else []
    fc = content.function_chars()
    shared = (tu.content_bigrams(first["idea"], remove=names, function_chars=fc)
              & tu.content_bigrams(hint, remove=names, function_chars=fc))
    if len(shared) < 2:
        return obj
    return dict(obj, twists=[dict(first, card=True)] + list(twists[1:]))


def apply_secret(book: Book, obj: dict) -> None:
    """Only usable twists reach the director (rejected twists never reach the writer): at most three, in the model's
    order, bound one per fork-1 branch (A, B, C; fewer twists repeat) so sibling world lines get different twists — and
    the card's truth (marked by mark_card_twist) first, bound to A and B, another twist to C (findings #5 fix 4: the
    card truths are the simple, warm ones)."""
    twists = _usable_twists(book, obj.get("twists"))
    card = next((i for i, t in enumerate(twists) if t.get("card") is True), None)
    if card is not None:
        twists.insert(0, twists.pop(card))
        bound = {"n.A": 0, "n.B": 0, "n.C": 1 if len(twists) > 1 else 0}
    else:
        bound = {f"n.{b}": i % len(twists) for i, b in enumerate("ABC")} if twists else {}
    book.secret = BibleSecret(payoffs={str(k): v for k, v in _dict(obj.get("payoffs")).items() if isinstance(v, str)},
                              twists=twists,
                              endings={str(k): v for k, v in _dict(obj.get("endings")).items() if isinstance(v, str)},
                              twist_by_branch=bound,
                              low=obj["low"].strip() if isinstance(obj.get("low"), str) else "")


def reset_opening(book: Book) -> None:
    root = book.nodes["n"]
    if root.pages:
        raise ValueError("cannot reset an opening that already has pages")
    book.bible, book.secret = None, None
    root.ledger, root.choice, root.state = [], None, StoryState()


def apply_plan(node: Node, obj: dict) -> None:
    node.plan = str(obj.get("text", ""))[:120]


def _enter(book: Book, state: StoryState, ledger: list[LedgerItem], option: Option) -> None:
    """What taking an option adds to its world line: a quality, an idea item, and the cameo character it brings
    (state.cast_extra; the book's cast never changes)."""
    q = QUALITY.get(option.kind)
    if q:
        state.qualities[q] = state.qualities.get(q, 0) + 1
    if option.kind == "idea" and option.token:
        ledger.append(LedgerItem(id=f"I{sum(1 for x in ledger if x.kind == 'idea') + 1}", kind="idea",
                                 what=option.token, status="planted", planted_text=option.text))
    cast = book.bible.cast if book.bible else []
    if option.cameo and option.cameo not in cast and option.cameo not in state.cast_extra:
        state.cast_extra.append(option.cameo)


def new_child(content: Content, book: Book, parent_id: str, option: Option) -> Node:
    cid = child_id(parent_id, option.id)
    if cid in book.nodes:
        return book.nodes[cid]
    parent = book.nodes[parent_id]
    chapter = parent.chapter + 1
    layout = content.layout(book.length)
    role = layout[chapter - 1][1] if chapter <= len(layout) else ""
    log = list(parent.choice_log) + [{"node": parent_id, "option": option.id, "kind": option.kind, "text": option.text,
                                      "hint": option.hint, "token": option.token, "chapter": parent.chapter}]
    node = Node(id=cid, parent=parent_id, via=option.id, chapter=chapter, role=role, state=parent.state.copy(),
                ledger=[LedgerItem.from_dict(x.to_dict()) for x in parent.ledger], choice_log=log)
    _enter(book, node.state, node.ledger, option)
    book.nodes[cid] = node
    return node


def planned(pages) -> int:
    """How many of the chapter's planned pages `pages` hold: the second half of a split page (CONT) belongs to the page
    before it, so a chapter may have one page more than its plan."""
    return sum(1 for p in pages if CONT not in p.fixes)


def chapter_size(book: Book, node: Node) -> int:
    """How many pages node's chapter has: its layout size plus the second half of each page split in code (CONT). Both
    halves are committed together, so this holds while the chapter streams too. A reader's views count from it — the
    chapter's last page, its next page, the fork and the end, the pages shown before the node is done, the finale's last
    page that marks its ending read — never from the layout alone: with a split page the layout's last page leads nowhere
    (M3 r3 review, contract-R3C-1)."""
    sizes = book.chapter_sizes()
    base = sizes[node.chapter - 1] if 1 <= node.chapter <= len(sizes) else planned(node.pages)
    return base + sum(1 for p in node.pages if CONT in p.fixes)


def page_number(book: Book, node: Node, idx: int) -> int:
    """The number a reader sees on node's page idx (1-based): planned pages are counted, so the second half of a split
    page keeps its page's number and the book's last page is still sum(book.chapter_sizes())."""
    return book.first_page_number(node.chapter) + planned(node.pages[:idx]) - 1


def start_of(pages, k: int) -> int:
    """How many pages come before the planned page k (0-based): a rewrite from that planned page keeps these."""
    seen = 0
    for i, p in enumerate(pages):
        if CONT not in p.fixes:
            if seen == k:
                return i
            seen += 1
    return len(pages)


def gone_items(state: StoryState) -> list[str]:
    """Items this world line has lost and not got back (what the validator and the state block call 已经没有了)."""
    held = {item_core(x) for x in state.items}
    return [x for x in state.removed if item_core(x) not in held]


def item_name(book: Book, ledger, name: str) -> str:
    """An item as the story names it: a setup or ledger id the model wrote as an item (r1 002 items_add ["S1"], so the
    briefs said 「手里的东西：S1、S2」) is the thing itself (thing_name of its what, M3 r2 #12); anything else as given."""
    s = resolve_id(book.bible, ledger, name.strip()) if isinstance(name, str) else None
    return thing_name(s["what"]) if s is not None and s.get("what") else name


def _add_item(state: StoryState, name: str) -> None:
    if name not in state.items:
        state.items.append(name)
    core = item_core(name)
    state.removed = [x for x in state.removed if item_core(x) != core]       # it is back


def _remove_item(state: StoryState, name: str, keep=frozenset(), exact: bool = False) -> str | None:
    """Removes the held item `name` means and records it in state.removed; returns it, or None when nothing matched.
    An exact match (parenthesised remarks ignored) wins; else (unless `exact`: a setup id names one thing) the single
    best partial match in either direction that shares ≥2 CJK characters (most shared, then the closest length, then
    the earliest). Items whose name is in `keep` (planted ledger items this delta does not pay) are never removed by a
    partial match."""
    core = item_core(name)
    if not core:
        return None
    hit = next((it for it in state.items if it == name or item_core(it) == core), None)
    if hit is None and not exact:
        best = None
        for i, it in enumerate(state.items):
            ic = item_core(it)
            if not ic or ic in keep or not (core in ic or ic in core):
                continue
            shared = tu.cjk_len(min(core, ic, key=len))
            score = (shared, -abs(len(ic) - len(core)), -i)
            if shared >= 2 and (best is None or score > best[0]):
                best = (score, it)
        hit = best[1] if best else None
    if hit is not None:
        state.items.remove(hit)
        state.removed.append(hit)
    return hit


def apply_page(content: Content, book: Book, node: Node, obj: dict, ctx: PageCtx, clue: str = "") -> Page:
    """Appends a settled page; its `_meta` fixes and residual codes (`residual:<code>`) go into page.fixes."""
    idx = len(node.pages) + 1
    lines = [Line(k=l.get("k", ""), text=l.get("text", ""), who=l.get("who")) for l in as_list(obj.get("lines"))
             if isinstance(l, dict)]
    delta = obj.get("delta") if isinstance(obj.get("delta"), dict) else {}
    meta = _dict(obj.get("_meta"))
    fixes = [str(x) for x in as_list(meta.get("fixes"))] + [f"residual:{c}" for c in as_list(meta.get("residual"))]
    page = Page(id=page_id(node.id, idx), lines=lines, art=ArtBrief.from_dict(obj.get("art", {})), delta=dict(delta),
                summary=str(obj.get("sum", ""))[:30], fixes=fixes)
    if idx == 1 and node.via:
        page.stamp = node.via
    node.pages.append(page)
    for k, n in count_usage(obj, ctx).items():
        node.state.bump(k, n)
    paid = {x for x in as_list(delta.get("payoff")) if isinstance(x, str)}
    keep = {item_core(x.what) for x in node.ledger if x.status == "planted" and x.id not in paid and x.what}
    for it in as_list(delta.get("items_add")):
        if isinstance(it, str) and it:
            _add_item(node.state, item_name(book, node.ledger, it))
    for it in as_list(delta.get("items_remove")):
        if isinstance(it, str) and it:
            name = item_name(book, node.ledger, it)
            _remove_item(node.state, name, keep, exact=name != it)      # an id: its own thing or nothing
    for f in as_list(delta.get("flags")):
        if isinstance(f, str) and f and f not in node.state.flags:
            node.state.flags.append(f)
    text = page.text()
    for sid in as_list(delta.get("plant")):
        for item in node.ledger:
            if item.id == sid and item.status == "planned":
                item.status, item.planted_page, item.planted_text = "planted", page.id, text[:60]
    for sid in paid:
        for item in node.ledger:
            if item.id == sid:
                item.status = "paid"
    if clue and clue_shown(content, book.bible, clue, text):     # a record: the director reads the whole line
        node.state.bump("twist_clue")                              # (director.clue_planted, chapter 1 too)
    return page


def _id(x, default: str) -> str:
    return x if isinstance(x, str) and x else default


def apply_choice(book: Book, node: Node, obj: dict, ctx: ForkCtx) -> ChoicePoint:
    """The fork as the child gets it: its strings as strings (validate.first_str), never a repr (M3 r3 review R3-ROB-3);
    an id or a kind of another shape is the default one."""
    opts = [Option(id=_id(o.get("id"), "ABC"[i] if i < 3 else f"X{i + 1}"), kind=_id(o.get("kind"), "careful"),
                   text=first_str(o.get("text")), hint=first_str(o.get("hint")), token=first_str(o.get("token")))
            for i, o in enumerate(x for x in as_list(obj.get("opts")) if isinstance(x, dict))]
    cp = ChoicePoint(question=first_str(obj.get("q")), options=opts,
                     ideas=[x for x in as_list(obj.get("ideas")) if isinstance(x, str)][:2], axis=str(ctx.fork_index),
                     fixes=[str(x) for x in as_list(_dict(obj.get("_meta")).get("fixes"))])
    for k, n in count_fork_usage(obj).items():
        node.state.bump(k, n)
    node.choice = cp
    return cp


def _chosen(book: Book, entry: dict) -> tuple[str, str]:
    """A choice as the recap says it: (verb, words). A child's idea is 「你想到了」 in the child's own words (Option.label)
    when it has them, else its decision without the 「X决定：」 frame (an unsafe idea has no label); a menu option is
    「你选了」 its text."""
    parent = book.nodes.get(entry.get("node"))
    opt = parent.choice.option(entry.get("option")) if parent is not None and parent.choice is not None else None
    text = str(entry.get("text", "")).strip()
    if entry.get("kind") == "idea" or (opt is not None and opt.kind == "idea"):
        label = opt.label.strip() if opt is not None and opt.text == entry.get("text") else ""
        return "你想到了", label or DECISION.sub("", text)
    return "你选了", text


def got_on_line(book: Book, node: Node, token: str) -> bool:
    """The token is a thing this world line really got: an item it held (held now or lost since) or a setup it planted,
    by name — never an action (validate.action_token), never an idea's own token (r1 005's hug 「得到了「飞天大沙发」」 when
    the hug missed). M3 r2 #4, findings #10 fix 4."""
    core = item_core(token)
    if tu.cjk_len(core) < 2 or action_token(core):
        return False
    held = [item_core(item_name(book, node.ledger, x)) for x in list(node.state.items) + list(node.state.removed)]
    held += [thing_name(x.what) for x in node.ledger if x.kind == "setup" and x.status != "planned" and x.what]
    return any(h == core or (tu.cjk_len(h) >= 2 and (h in core or core in h)) for h in held if h)


RECAP_PLAIN = ("一开始，你帮他们选了一条路。", "后来，你又帮他们出了一个主意——这一招真管用！", "最后，故事走到了结尾。")


def recap_lines(book: Book, node: Node, content: Content | None = None) -> list[str]:
    """Exactly three lines for the ending page (read aloud): the first choice, the last one (with one fork: what it
    brought, or that the child decided), and where the story ended — 「一开始，你选了「…」。」, 「后来，你想到了「{label}」——这一招
    真管用！」 (M3 r2 #4, findings #6 fix 4, #10 fix 4). 「还拿到了「X」」 only for a thing this line really got (got_on_line) that
    the quoted words do not already name; r1 said 「得到了「捂耳朵」」. With content, a line that would quote a display
    problem (check_strings: a soft residual left in an option, the child's own words) is said without the quote, after
    the fixed replacements the fork makes in code (swap_words)."""
    log = [e for e in node.choice_log if str(e.get("text", "")).strip()]
    title = node.ending.title if node.ending else ""

    def ok(line: str) -> bool:
        return content is None or not check_strings([line], content)

    last = f"最后，故事走到了「{title}」。"
    last = last if ok(last) else RECAP_PLAIN[2]                # the ending's name too (M3 r3 review, R3-ROB-6)
    if not log:
        return ["你从第一页一直读到了最后。", "一路上发生了好多事。", last]

    def said(entry: dict) -> tuple[str, str]:
        verb, words = _chosen(book, entry)
        words = swap_words(words, content) if content is not None else words      # 内壁 → 墙上, as on the fork
        tok = str(entry.get("token", "")).strip()
        got = tok if tok and got_on_line(book, node, tok) and tok not in words + str(entry.get("text", "")) else ""
        return f"{verb}「{words}」" + (f"，还拿到了「{got}」" if got else ""), got

    first, got0 = said(log[0])
    one = f"一开始，{first}。"
    one = one if ok(one) else RECAP_PLAIN[0]
    if len(log) == 1:
        two = f"「{got0}」一直陪着你。" if got0 else "这一路，都是你自己拿的主意。"
    else:
        two = f"后来，{said(log[-1])[0]}——这一招真管用！"
        two = two if ok(two) else RECAP_PLAIN[1]
    return [one, two, last]


def apply_end(book: Book, node: Node, obj: dict, family: str, content: Content | None = None) -> Ending:
    """Writes the ending; never marks the node done (the caller's job) or the ending found (mark_ending_read). The
    writer passes content, so the recap is checked like every other display string (recap_lines)."""
    node.ending = Ending(title=str(obj.get("title", "")).strip(), family=family)
    node.ending.recap = recap_lines(book, node, content)
    node.family = family
    return node.ending


def mark_ending_read(book: Book, node: Node) -> None:
    """The child has read this ending (its last page was shown): book.endings_found gets it once."""
    if node.ending is None or any(e.get("node") == node.id for e in book.endings_found):
        return
    book.endings_found.append({"node": node.id, "family": node.ending.family, "title": node.ending.title})


def _initial_state(book: Book, node: Node) -> tuple[StoryState, list[LedgerItem]]:
    if node.parent is None:
        return StoryState(), _setup_ledger(book)
    parent = book.nodes[node.parent]
    state = parent.state.copy()
    ledger = [LedgerItem.from_dict(x.to_dict()) for x in parent.ledger]
    opt = parent.choice.option(node.via) if parent.choice else None
    if opt is not None:
        _enter(book, state, ledger, opt)
    return state, ledger


def truncate(content: Content, book: Book, node: Node, keep: int, clue: str = "") -> None:
    kept = node.pages[:keep]
    node.pages, node.choice, node.ending = [], None, None
    node.state, node.ledger = _initial_state(book, node)
    for p in kept:
        obj = {"type": "page", "lines": [l.to_dict() for l in p.lines], "art": p.art.to_dict(), "delta": p.delta,
               "sum": p.summary}
        ctx = PageCtx(content=content, bible=book.bible, state=node.state, chapter=node.chapter,
                      page_in_chapter=len(node.pages) + 1, pages_in_chapter=max(keep, 1), is_final_chapter=False,
                      ledger=tuple(node.ledger))
        restored = apply_page(content, book, node, obj, ctx, clue)
        restored.image, restored.audio, restored.fixes, restored.stamp = p.image, p.audio, p.fixes, p.stamp


def used_phrases(content: Content, node: Node) -> list[str]:
    return sorted(g["key"] for g in content.tier_b() if node.state.count("tierb:" + g["key"]))


def apply_event(content: Content, book: Book, event) -> None:
    """Mirrors a writer Event. page/choice/end/truncate carry the node's state and ledger after the change; a page
    the copy already has changes nothing (a replayed event's snapshot is older). "done" sets the status (and the
    node's usage notes); "end" never does."""
    k, d = event.kind, event.data
    if k == "title":
        apply_title(book, d)
    elif k == "world":
        apply_world(book, d, content)
    elif k == "setups":
        apply_setups(book, d)
    elif k == "secret":
        apply_secret(book, d)
    elif k == "reset":
        reset_opening(book)
    elif k == "plan_meta":
        node = book.nodes[event.node]
        node.role, node.outcome = d.get("role", node.role), d.get("outcome", node.outcome)
        node.family = d.get("family", node.family)
    elif k == "plan":
        apply_plan(book.nodes[event.node], d)
    elif k == "done":
        node = book.nodes[event.node]
        node.status = "done"
        node.usage.update(_dict(d.get("usage")))
    elif k in ("page", "choice", "end", "truncate"):
        node = book.nodes[event.node]
        if k == "page":
            page = Page.from_dict(d["page"])
            if any(p.id == page.id for p in node.pages):
                return
            node.pages.append(page)
        elif k == "choice":
            node.choice = ChoicePoint.from_dict(d["choice"])
        elif k == "end":
            node.ending = Ending.from_dict(d["ending"])
            node.family = node.ending.family
        elif k == "truncate":
            node.pages, node.choice, node.ending = node.pages[:int(d["keep"])], None, None
        node.state = StoryState.from_dict(d["state"])
        node.ledger = [LedgerItem.from_dict(x) for x in d["ledger"]]
