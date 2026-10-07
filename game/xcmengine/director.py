"""The director: turns the story skeleton (beats.json) plus branch state into lean chapter plans and
briefs, gives fork siblings different outcomes, schedules setups, ideas and the twist, and picks ending families."""
from __future__ import annotations

import itertools
import math
import random
import re
from dataclasses import dataclass, field

from . import textutil as tu
from .content import Content
from .models import Book, Node, Option, path_ids
from .validate import clue_shown, resolve_id

OUTCOMES = ("success_with_cost", "fail_but_gain", "detour")
MIDDLE = ("trouble", "detour", "lowpoint", "lowpoint_short")
LOW = ("lowpoint", "lowpoint_short")
HOOKS = ("question", "interrupted", "reveal", "joke", "quiet")
FAMILIES = ("warm", "twist", "funny")
_CN = "零一二三四五六七八九"


def cn(n: int) -> str:
    if n < 10:
        return _CN[n]
    if n < 20:
        return "十" + (_CN[n % 10] if n % 10 else "")
    return _CN[n // 10] + "十" + (_CN[n % 10] if n % 10 else "")


@dataclass
class PageBeat:
    number: int
    index: int
    beat: str
    hook: str
    tension: int


@dataclass
class ChapterPlan:
    chapter: int
    role: str
    structure: str
    pages: list[PageBeat]
    is_final: bool
    outcome: str = ""
    chosen: Option | None = None
    clue: str = ""
    reveal: str = ""                                        # the twist this chapter tells on its page 2
    reserve: list[str] = field(default_factory=list)
    due_payoffs: list[str] = field(default_factory=list)
    bans: list[str] = field(default_factory=list)
    fork_axis: str = ""
    final_fork: bool = False
    ending: dict = field(default_factory=dict)
    needs_rule: bool = False
    must_plant: list[str] = field(default_factory=list)     # the turn setup while it is still only planned
    due_what: dict = field(default_factory=dict)            # id → what for every id the brief names (bible or ledger)
    absent: list[str] = field(default_factory=list)         # cast members (and "guest") not entered yet (chapter ≥ 2)
    hero: str = ""                                          # the hero's name; "主角" before the bible has one
    want: str = ""                                          # bible.want ("" before the world line exists)
    card_hook: str = ""                                     # the card's opening line (chapter 1)


def outcomes_for(seed: str, option_ids: list[str]) -> dict[str, str]:
    """The menu options' outcome variants (seeded, all different); a child's idea (P…) always gets "idea": it comes true
    first, trouble only after (M3 r2 #14 — 「成功了一半」 set r1 005's hug up to fail)."""
    rng = random.Random(f"{seed}|outcomes")
    order = list(OUTCOMES)
    rng.shuffle(order)
    menu = [i for i in option_ids if not i.startswith("P")]
    out = {oid: order[k % len(order)] for k, oid in enumerate(menu)}
    for oid in option_ids:
        if oid.startswith("P"):
            out[oid] = "idea"
    return out


FORK_PAGE_HOOKS = ("question", "quiet")       # a chapter's last page before its fork: the fork asks the rest
AFTER_TURN_HOOKS = ("joke", "quiet")          # the finale's pages after the turn: no new trouble
LOW_OPEN_HOOKS = ("question", "interrupted", "reveal")   # the low point's page 1: its page 2 is the quiet truth page


def page_hooks(seed: str, layout) -> dict[int, str]:
    """Page number → hook for the whole book (seeded; never the same hook twice in a row). The last page of a chapter
    that ends in a fork asks a question or goes quiet: an interrupted action or a reveal left hanging was finished by
    the fork question instead (r1 003 「…（嗖！）」 → 「树洞叼走口哨，怎么夺回来？」). The finale's pages after its first (the
    turn) only end on a joke or a quiet moment: a threat there opened a new trouble after the turn (r1 004 「那个喷嚏死灰
    复燃」). The low point's page 1 asks, breaks off or is about to reveal: a joke set up for its quiet truth page, or a
    quiet end promising 「下一页会很热闹」, fought that page (the review's R2CHK-13). The book's last page has none."""
    rng = random.Random(f"{seed}|hooks")
    out: dict[int, str] = {}
    last, number = None, 0
    for k, (pages, role) in enumerate(layout):
        finale = k == len(layout) - 1
        for i in range(1, pages + 1):
            number += 1
            if finale and i == pages:
                out[number] = ""
                continue
            allowed = (AFTER_TURN_HOOKS if finale and i > 1 else FORK_PAGE_HOOKS if i == pages
                       else LOW_OPEN_HOOKS if role in LOW else HOOKS)
            last = out[number] = rng.choice([h for h in allowed if h != last] or list(allowed))
    return out


def twist_for(book: Book, parent: Node | None, chosen: Option | None) -> dict | None:
    twists = [t for t in (book.secret.twists if book.secret else []) if t.get("idea") and t.get("clue")]
    if not twists:
        return None
    if parent is None:
        return twists[0]
    ids = path_ids(parent.id)
    branch = ids[1].split(".")[-1] if len(ids) > 1 else (chosen.id if chosen else "A")
    bound = (book.secret.twist_by_branch or {}).get(f"n.{branch}")
    if isinstance(bound, int) and 0 <= bound < len(twists):
        return twists[bound]
    idx = "ABC".index(branch) if branch in ("A", "B", "C") else 0
    return twists[idx % len(twists)]


def _bans(content: Content, parent: Node | None, memory_phrases) -> list[str]:
    state = parent.state if parent else None
    bans: list[str] = []
    for g in content.tier_b():
        over = state is not None and state.count("tierb:" + g["key"]) >= g["max_per_book"]
        remembered = any(v in memory_phrases for v in g["variants"])
        if over or remembered:
            bans.append(g["key"])
    if state is not None:
        for cid, card in content.characters.items():
            for tic in card.get("tics", []):
                core = "".join(ch for ch in tic["text"] if "一" <= ch <= "鿿")
                if state.count("tic:" + core) >= int(tic["max_per_book"]):
                    bans.append(tic["text"].rstrip("！!。"))
    return bans[:8]


def score_endings(content: Content, book: Book, path: list[Node], extra_kind: str = "",
                  memory_families=()) -> dict[str, float]:
    cfg = content.beats["endings"]
    last = path[-1] if path else None
    kinds = [e.get("kind") for e in (last.choice_log if last else [])] + ([extra_kind] if extra_kind else [])
    flags = " ".join(f for n in path for f in n.state.flags)
    ledger = last.ledger if last else []
    found = {e.get("family") for e in book.endings_found}
    out: dict[str, float] = {}
    for fam in FAMILIES:
        rules = cfg["score"][fam]
        s = float(sum(rules.get("kinds", {}).get(k, 0) for k in kinds))
        if fam == "warm":
            s += sum(1 for w in rules.get("flag_words", []) if w in flags)
            s += rules.get("promise_paid", 0) * sum(1 for x in ledger if x.kind == "promise" and x.status == "paid")
        elif fam == "twist":
            planted = last is not None and clue_planted(content, book, last, twist_for(book, last, None))
            s += rules.get("twist_clue_planted", 0) * (1 if planted else 0)
        elif fam == "funny":
            s += rules.get("gag_paid", 0) * sum(1 for x in ledger if x.role == "gag" and x.status == "paid")
        if fam in found:
            s -= cfg["novelty_penalty_found_in_book"]
        if fam in set(memory_families):
            s -= cfg["novelty_penalty_recent_books"]
        out[fam] = s
    return out


def _story_names(content: Content, book: Book, node: Node | None) -> list[str]:
    b = book.bible
    if b is None:
        return []
    cast = list(b.cast) + list(node.state.cast_extra if node is not None else [])
    names = [content.name(x) for x in cast if isinstance(x, str)] + list(b.places)
    if b.has_guest():
        names.append(str(b.guest.get("name", "")))
    return [n for n in names if n]


def clue_planted(content: Content, book: Book, node: Node | None, twist: dict | None) -> bool:
    """The bound twist's clue is on this world line, chapter 1 included (the bible's clue may be a chapter-1 detail: r1
    001's is n.p3 「落叶响，真好听。」): a page of the line shows it (validate.clue_shown — two content bigrams, or its head
    noun, names and places out). The twist family, its evidence and the path score open only then: r1 004 n.C's clue never
    appeared, and its ending revealed a truth from nowhere (findings #7, the lead's ruling)."""
    if not twist or node is None:
        return False
    clue = str(twist.get("clue") or "")
    return any(clue_shown(content, book.bible, clue, p.text()) for p in book.pages_on_path(node.id))


def family_evidence(content: Content, book: Book, parent: Node, opt: Option) -> dict[str, float]:
    """Evidence for each ending family from this option alone: its text/hint/token reusing what this world line has
    planted (a gag item → funny; a promise or idea item, or a warm flag word → warm; the bound twist's clue or setup,
    only once the clue is on this line (clue_planted) → twist) plus the kind bonus. Book history is never evidence."""
    rules = content.beats["endings"]["score"]
    fc, names = content.function_chars(), _story_names(content, book, parent)
    words = f"{opt.text} {opt.hint} {opt.token}"
    own = tu.content_bigrams(words, remove=names, function_chars=fc)

    def reuses(what) -> bool:
        return bool(own & tu.content_bigrams(str(what or ""), remove=names, function_chars=fc))

    out = {f: float(rules[f].get("kinds", {}).get(opt.kind, 0)) for f in FAMILIES}
    seen = [x for x in parent.ledger if x.status != "planned"]          # planted (or already paid) on this line
    if any(x.role == "gag" and reuses(x.what) for x in seen):
        out["funny"] += rules["funny"].get("gag_paid", 2)
    if (any(x.kind in ("promise", "idea") and reuses(x.what) for x in seen)
            or any(w in words for w in rules["warm"].get("flag_words", []))):
        out["warm"] += rules["warm"].get("promise_paid", 2)
    twist = twist_for(book, parent, None)
    if twist and clue_planted(content, book, parent, twist):
        setup = book.bible.setup(twist.get("setup")) if book.bible else None
        if reuses(twist.get("clue")) or (setup is not None and reuses(setup.get("what"))):
            out["twist"] += rules["twist"].get("twist_clue_planted", 2)
    return out


def _pool(content: Content, book: Book, parent: Node) -> tuple[str, ...]:
    """twist only with a bound twist whose clue is on this world line (clue_planted) — or in a book without a secret,
    the lean writer's (M3 r3): it has no clue machinery, and the card's truth (「意外真相」) is in every one of its
    requests, so all three families are open and the three menu options of the final fork end three ways."""
    if book.secret is None:
        return FAMILIES
    return FAMILIES if clue_planted(content, book, parent, twist_for(book, parent, None)) else ("warm", "funny")


def _novelty(content: Content, book: Book, memory_families) -> dict[str, float]:
    cfg = content.beats["endings"]
    found, recent = {e.get("family") for e in book.endings_found}, set(memory_families)
    return {f: (cfg["novelty_penalty_found_in_book"] if f in found else 0)
            + (cfg["novelty_penalty_recent_books"] if f in recent else 0) for f in FAMILIES}


def _best(scores: dict, pool, tie) -> str:
    return max(pool, key=lambda f: (scores[f], -tie.index(f)))


def _own_family(content: Content, book: Book, parent: Node, opt: Option, memory_families=()) -> str:
    """An option's own best family, novelty penalties included (idea options, and the finale fallback)."""
    pool, pen = _pool(content, book, parent), _novelty(content, book, memory_families)
    ev = family_evidence(content, book, parent, opt)
    return _best({f: ev[f] - pen[f] for f in pool}, pool, content.beats["endings"]["tie_break"])


def _draw(perms: list, totals: list, temperature: float, seed: str, tie) -> tuple:
    """One permutation with probability ∝ exp(total / temperature); argmax (ties by tie_break) when it is ≤ 0."""
    if temperature <= 0:
        return max(zip(totals, perms), key=lambda tp: (tp[0], tuple(-tie.index(f) for f in tp[1])))[1]
    top = max(totals)
    weights = [math.exp((t - top) / temperature) for t in totals]
    r = random.Random(seed).random() * sum(weights)
    for perm, w in zip(perms, weights):
        r -= w
        if r < 0:
            return perm
    return perms[-1]


def assign_families(content: Content, book: Book, parent: Node, memory_families=()) -> dict[str, str]:
    """Option id → ending family at the final fork. The menu options (A–C) get distinct families, one permutation drawn
    by a seeded softmax over the permutation totals of their own evidence (seed book.id|parent.id, T from
    beats.endings.temperature): the mapping never moves when the child finds endings or across books. Without a usable
    twist the pool is warm/funny and each option takes its own best. Idea options (P1…) take their own best, novelty
    penalties included."""
    cfg = content.beats["endings"]
    opts = parent.choice.options if parent.choice else []
    tie, pool = cfg["tie_break"], _pool(content, book, parent)
    ev = {o.id: family_evidence(content, book, parent, o) for o in opts}
    menu = [o.id for o in opts if not o.id.startswith("P")][:len(FAMILIES)]
    out: dict[str, str] = {}
    if menu and pool == FAMILIES:
        perms = list(itertools.permutations(FAMILIES, len(menu)))
        totals = [sum(ev[i][f] for i, f in zip(menu, perm)) for perm in perms]
        out = dict(zip(menu, _draw(perms, totals, float(cfg.get("temperature", 2.0)), f"{book.id}|{parent.id}", tie)))
    else:
        out = {i: _best(ev[i], pool, tie) for i in menu}
    for o in opts:                                   # idea options (P1…) take their own best family
        if o.id not in out:
            out[o.id] = _own_family(content, book, parent, o, memory_families)
    return out


def _first_picture(book: Book) -> str:
    """Page 1's picture (place, focus) for the last page to come back to — never its first sentence, which is the
    trouble itself: the writer copied it and replayed the trouble (r1 001's three endings, M3 r2 #13)."""
    root = book.nodes.get("n")
    if not root or not root.pages:
        return ""
    art = root.pages[0].art
    return "，".join(x for x in (str(art.place or "").strip(), str(art.focus or "").strip()) if x)


_LEADS = re.compile(r"^(就在这时|这时候|这时|突然|忽然|接着|然后|于是|只见|原来|后来|不一会儿|一会儿)")
_INTRO = re.compile(r"[一两几](只|个|位|群|头|条|朵|块|团|颗|根|张|把|匹|棵|片|对|架|辆|艘|台)([^，。！？]{0,8}的)?$")
_CLAUSE = re.compile(r"[。！？!?；;，,：:…—～~\s“”‘’「」『』（）()]+")
_JOIN = ("还有", "和", "跟", "与", "同", "、")


def _names_of(content: Content, book: Book, who: str) -> list[tuple[str, list[str]]]:
    """(name, false friends) pairs a page uses for `who` (a canon id, or "guest" for the book's guest), longest first."""
    if who == "guest":
        g = book.bible.guest.get("name") if book.bible is not None and isinstance(book.bible.guest, dict) else ""
        return [(g, [])] if isinstance(g, str) and g else []
    return sorted(((n, content.false_friends(who)) for n in content.names(who)), key=lambda x: -len(x[0]))


def _name_at(text: str, pos: int, names) -> str:
    return next((n for n, ff in names if text.startswith(n, pos) and not any(text.startswith(f, pos) for f in ff)), "")


def appeared(content: Content, book: Book, who: str, pages) -> bool:
    """`who` (a cast id, or "guest") has entered the story in words on these pages: a line of their own, or narration
    with the name at the head of a clause (「吉吉国王荡下来」, 「毛毛和熊二一起…」, after 这时/突然…, never 「熊大的斧头…」) or
    introducing it (「飞来一只雾哨鸟」, 「一台会唱歌的旧收音机」). A name in passing is not an entrance: r1 001's 熊大 was only named
    (「那是熊大刻给他的」) and was suddenly there on page 4 (M3 r2 #10, findings #9)."""
    mine = _names_of(content, book, who)
    everyone = sorted([x for cid in list(content.characters) + list(content.minor) for x in _names_of(content, book, cid)]
                      + _names_of(content, book, "guest"), key=lambda x: -len(x[0]))
    for p in pages:
        for l in p.lines:
            if l.k == "say" and l.who == who:
                return True
            if l.k != "narr" or not isinstance(l.text, str):
                continue
            for clause in _CLAUSE.split(l.text):
                c, pos = _LEADS.sub("", clause), 0
                while pos < len(c):                      # the names that open the clause: 「毛毛和熊二…」
                    hit = _name_at(c, pos, mine)
                    if hit:
                        if not c.startswith("的", pos + len(hit)):
                            return True
                        break
                    other = _name_at(c, pos, everyone)
                    if not other:
                        break
                    pos += len(other)
                    pos += len(next((j for j in _JOIN if c.startswith(j, pos)), ""))
                for i in range(len(c)):
                    if _name_at(c, i, mine) and _INTRO.search(c[:i]):
                        return True
    return False


def absent_cast(content: Content, book: Book, pages) -> list[str]:
    """The book's cast members, then its guest ("guest"), who have not entered in words on these pages (appeared)."""
    if book.bible is None:
        return []
    who = [cid for cid in book.bible.cast if isinstance(cid, str) and cid in content.characters]
    if _names_of(content, book, "guest"):
        who.append("guest")
    return [w for w in who if not appeared(content, book, w, pages)]


def _family(content: Content, book: Book, parent: Node, chosen: Option | None, memory_families=()) -> str:
    """The finale's ending family: the one the parent's fork gave the chosen option, else the option's own best (an
    idea not on the fork), else the best score of the path."""
    fams = assign_families(content, book, parent, memory_families) if parent.choice else {}
    family = fams.get(chosen.id) if chosen else None
    if not family and chosen is not None:            # not on the parent's fork: the chosen option's own best
        family = _own_family(content, book, parent, chosen, memory_families)
    if not family:
        s = score_endings(content, book, book.path(parent.id), "", memory_families)
        tie = content.beats["endings"]["tie_break"]
        family = max(FAMILIES, key=lambda f: (s[f], -tie.index(f)))
    return family


def all_names(content: Content, book: Book) -> list[str]:
    """Every name a page may use for someone or somewhere: canon characters (aliases and minor ones too), the guest and
    the book's places."""
    b = book.bible
    out = [n for cid in list(content.characters) + list(content.minor) for n in content.names(cid)]
    if b is not None:
        out += [p for p in b.places if isinstance(p, str)] if isinstance(b.places, list) else []
        guest = b.guest.get("name") if isinstance(b.guest, dict) else ""
        out += [guest] if isinstance(guest, str) else []
    return [n for n in out if n]


def finale_callback(book: Book, parent: Node, chosen: Option | None, names=()) -> str:
    """What the finale brings back once: a thing this world line planted and has not used — the oldest idea of the
    child's (it outranks; never one whose thing is one of `names`: a character is no thing, R2CHK-8), else a gag or
    clue setup — never the turn, never what the chosen option already uses, and never a choice token: tokens are often
    actions, and r1 001 re-enacted 「捂耳朵」 on page 11 (M3 r2 #4)."""
    turn = book.bible.turn_setup() if book.bible else None
    used = f"{chosen.text} {chosen.token}" if chosen is not None else ""
    planted = [x for x in parent.ledger if x.status == "planted" and x.what]
    ideas = [x for x in planted if x.kind == "idea" and x.what.strip() not in set(names)]
    setups = [x for x in planted if x.kind == "setup" and x.role in ("gag", "clue") and (not turn or x.id != turn.get("id"))]
    return next((x.what for x in ideas + setups if x.what not in used), "")


def _clue_sentence(content: Content, book: Book, pages, clue: str) -> str:
    """The sentence of this world line that planted the twist's clue: the one sharing the most content bigrams with it,
    two at least (names left out; the earliest on a tie), "" when none does. The reveal points back at it, so the truth
    comes from something the child already heard (r1 005: 「屋外的电话线晃了一下。」, read twice, never explained); one shared
    bigram pointed 002 n.B.B's truth at its page-1 trouble (「…王冠吹进了山洞。」, only 王冠: the review's R2CHK-14)."""
    fc, names = content.function_chars(), all_names(content, book)
    want = tu.content_bigrams(clue, remove=names, function_chars=fc)
    best, score = "", 1
    for p in pages:
        for l in p.lines:
            for s in tu.split_sentences(l.text) if l.k != "sfx" else []:
                n = len(want & tu.content_bigrams(s, remove=names, function_chars=fc))
                if n > score:
                    best, score = s, n
    return best


def plan_chapter(content: Content, book: Book, chapter: int, parent: Node | None = None,
                 chosen: Option | None = None, memory_phrases=frozenset(), memory_families=(),
                 family: str = "") -> ChapterPlan:
    """The plan of one chapter. Siblings differ by their outcome variant alone: a brief never says what the other
    options of the fork do (M3 r2 #1 — quoting them primed the writer to use them). `family` keeps a resumed finale on
    the ending family its committed pages were written for; else the finale's family is decided here."""
    layout = content.layout(book.length)
    n_ch = len(layout)
    pages_n, role = layout[chapter - 1]
    structure = book.seeds.get("structure", "three_tries")
    beats = content.structure(structure)["roles"][role]
    tension = content.beats["tension"][role]
    first = book.first_page_number(chapter)
    hooks = page_hooks(book.id, layout)
    hero = content.name(book.bible.hero) if book.bible and book.bible.hero else "主角"
    turn = book.bible.turn_setup() if book.bible else None
    turn_text = f"「{turn['what']}」" if turn else "前面埋下的东西"
    is_final = chapter == n_ch
    outcome = ""
    if chosen is not None and parent is not None and parent.choice is not None:
        ids = [o.id for o in parent.choice.options]
        outcome = outcomes_for(f"{book.id}|{parent.id}", ids).get(chosen.id, "success_with_cost")
    outcome_text = content.beats["outcomes"].get(outcome or "success_with_cost")
    if is_final and parent is not None and family not in FAMILIES:
        family = _family(content, book, parent, chosen, memory_families)
    families = content.beats["endings"]["families"]
    ending_beat = (families.get(family) or families["warm"]).get("page3", "")
    twist = twist_for(book, parent, chosen)
    reveal_ch = n_ch - 1 if n_ch >= 4 else n_ch       # the low point (a short book's follows fork 1: its truth waits)
    reveal = twist.get("idea", "") if twist and chapter == reveal_ch else ""     # told once (R2CHK-2)
    truth = twist.get("idea", "") if twist and is_final and family == "twist" and not reveal else ""  # told already
    picture, want = _first_picture(book), book.bible.want if book.bible else ""
    echo = (content.beats["echo"].replace("{picture}", f"（{picture}）" if picture else "")
            .replace("{want}", f"「{want}」" if want else "想要的东西"))
    told = reveal
    if reveal:                     # in a child's words (findings #5 fix 3), pointing back at the sentence of its clue
        clue = _clue_sentence(content, book, book.pages_on_path(parent.id) if parent else [], twist.get("clue", ""))
        told += "（用孩子听得懂的话说，不要照抄这句" + (f"；前面的线索：「{clue}」" if clue else "") + "）"
    pages = []
    for i in range(pages_n):
        beat = beats[i]
        if i == 0 and role in LOW and book.secret and book.secret.low:     # what every low point loses, told this line's way
            beat = f"{beat.replace('{low_menu}', '')}；低谷：{book.secret.low}，按这条路的经历来写"     # one loss, no menu
        beat = beat.replace("{low_menu}", content.beats.get("low_menu", ""))
        if reveal and i == 1:                          # the truth gets page 2: the low point's, or a short finale's
            beat = f"{beat}；{content.beats['reveal']['finale']}" if is_final else content.beats["reveal"]["page"]
        if truth and i == 2:                           # a twist ending after the low point told it: its surprise only
            beat = f"{beat}；{content.beats['reveal']['told'].replace('{truth}', truth)}"
        beat = (beat.replace("{reveal}", told).replace("{ending}", ending_beat).replace("{echo}", echo)
                .replace("{hero}", hero).replace("{turn_setup}", turn_text).replace("{outcome}", outcome_text))
        number = first + i
        pages.append(PageBeat(number, i + 1, beat, hooks[number], tension[i]))
    plan = ChapterPlan(chapter, role, structure, pages, is_final, outcome=outcome, chosen=chosen, reveal=reveal,
                       hero=hero, want=book.bible.want if book.bible else "",
                       card_hook=str(book.premise.get("hook") or "") if chapter == 1 else "")
    ledger = parent.ledger if parent else []
    own = ledger if parent is not None else (book.nodes["n"].ledger if "n" in book.nodes else [])  # ch. 1: the root's
    just_chosen = chosen if chosen is not None and chosen.kind == "idea" else None
    names = set(all_names(content, book))      # an idea whose thing is a name (r1 005's hug: 「飞天大沙发」, the guest) is
    ideas = [x for x in ledger if x.kind == "idea" and x.status == "planted" and x.what.strip() not in names   # no
             and not (just_chosen and x.what == just_chosen.token and x.planted_text == just_chosen.text)]    # thing
    idea = ideas[0] if ideas else None               # the oldest idea from an earlier fork (ledger is in story order)
    if turn and not is_final:
        plan.reserve = [turn["id"]]
        item = next((x for x in own if x.id == turn["id"]), None)
        if item is not None and item.status == "planned":
            plan.must_plant = [turn["id"]]
    if role in MIDDLE and idea is not None:          # gag and clue setups are never due here (M3 r2 #5): they stay
        plan.due_payoffs = [idea.id]                 # planted for the writer and the finale's callback
    if is_final and turn:
        plan.due_payoffs = [turn["id"]]
    if twist and chapter == 2 and reveal_ch > 2:
        plan.clue = twist.get("clue", "")
    if not is_final:
        plan.final_fork = chapter == n_ch - 1
        plan.fork_axis = content.beats["fork_axes"]["final" if plan.final_fork else str(min(chapter, 3))]
    plan.needs_rule = parent is None or parent.state.count("rule_uses") == 0
    if chapter > 1 and parent is not None:
        plan.absent = absent_cast(content, book, book.pages_on_path(parent.id))
    plan.bans = _bans(content, parent, memory_phrases)
    if is_final and parent is not None:     # no secret template (R2CHK-3): written before any branch, they fought the
        plan.ending = {"family": family, "turn": turn["what"] if turn else "",                  # rule and the want
                       "callback": finale_callback(book, parent, chosen, names), "echo": picture, "want": want,
                       **({"truth": truth} if truth else {})}
    for sid in plan.due_payoffs + plan.must_plant + plan.reserve:
        s = resolve_id(book.bible, own, sid)
        plan.due_what[sid] = s["what"] if s else ""
    return plan


def render_brief(plan: ChapterPlan, content: Content, book: Book) -> str:
    L = [f"【第{cn(plan.chapter)}章，共{cn(len(plan.pages))}页】"]
    hooks = content.beats["hooks"]
    for pb in plan.pages:
        beat = pb.beat
        if pb.index == 1 and plan.chosen is not None:
            beat = f"一开头就让读者看到「{plan.chosen.text}」带来的后果：{beat}（用自己的话写，不要照抄原话）"
        tail = f"结尾：{hooks[pb.hook]}。" if pb.hook else "这是全书的最后一页。"
        L.append(f"第{cn(pb.number)}页：{beat}。{tail}")
    if plan.chosen is not None and plan.chosen.kind == "idea":       # the child's own words came true (r1 005: 「扑了个空」)
        L.append("这是孩子自己想的点子：第一页就让它真的做成，" + ("用它解决难题。" if plan.is_final else "麻烦只能在做成以后出现。"))
    if plan.clue:
        L.append(f"本章悄悄埋下：{plan.clue}（写成一个不起眼的小细节，不要点破）。")

    def what(sid: str) -> str:
        return plan.due_what.get(sid) or (book.bible.setup(sid) or {}).get("what", "")

    for sid in plan.must_plant:              # where it goes is told here only (findings #8 fix 3: it goes stale)
        where = str((book.bible.setup(sid) or {}).get("where") or "").strip() if book.bible else ""
        L.append(f"本章不起眼地埋下：{sid}「{what(sid)}」" + (f"（埋在：{where}）" if where else "")
                 + "——放进一个动作里顺手带出来，写进文字和 art.focus，不要放在一页的最后一行，也不要用掉它。")
    for sid in plan.due_payoffs:
        s = book.bible.setup(sid) or {}
        if plan.is_final and s.get("role") == "turn":
            continue
        L.append(f"本章要让伏笔 {sid}「{what(sid)}」派上用场。")
    for sid in plan.reserve:
        if sid not in plan.must_plant:
            L.append(f"{sid}「{what(sid)}」留到最后关键时刻才用：在那之前它可以被看见、被提到，但不能拿它来解决问题，"
                     "岔路口的选项也不要用它。")         # seen, not used (r1 003: the turn whistle was option B of fork 1)
    if plan.needs_rule:      # the chosen option may set it off (r1 003: the trigger was a fork option, all siblings blew it)
        L.append("本章要让怪规矩真的起一次作用" + ("，最好就由刚才选的办法引出来。" if plan.chosen is not None else "。"))
    if plan.absent:                  # an entrance in words (r1: 熊大 and 赵琳 simply started talking from chapter 2 on)
        guest = book.bible.guest.get("name", "") if book.bible and isinstance(book.bible.guest, dict) else ""
        who = "、".join(guest if x == "guest" else content.name(x) for x in plan.absent)     # no example: an axe came
        L.append(f"本章让{who}出场：先各用一句旁白交代他们从哪儿来、正在做什么，再让他们各做一件和故事有关的事。"     # with it
                 if len(plan.absent) > 1 else                                                       # (R2CHK-6)
                 f"本章让{who}出场：先用一句旁白交代他从哪儿来、正在做什么，再让他做一件和故事有关的事。")
    if plan.bans:
        L.append("本章不用：" + "、".join(plan.bans) + "。")
    if plan.is_final:                # each thing once (R2CHK-7): the turn and the chosen way are page 9's beat, the
        e = plan.ending              # family's ending page 11's, the first picture with the want page 12's
        L.append("结局只能用这条路上已经出现过的人、东西和地方" + ("（要揭开的真相除外）" if plan.reveal else "")
                 + "；变没了、丢了、坏了的东西不能再出现，除非写清它怎么回来。")
        rule = str((book.bible.rule or {}).get("text") or "").strip().rstrip("。！!；;") if book.bible else ""
        if rule:            # r1 004's last page: a sneeze drove the train back, in a book where a sneeze stops it
            L.append(f"结局要守怪规矩「{rule}」：可以巧用，不能打破。")
        if e.get("callback"):
            L.append(f"让前面埋下的「{e['callback']}」在结尾再出现一次（用自己的话，不要照抄前面的句子）。")
        L.append("写完最后一页，输出 end 行。")
    else:
        L.append(f"最后给出岔路口：{plan.fork_axis}。")
    return "\n".join(L)
