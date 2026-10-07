"""Deterministic validation of model output lines: pages, forks, endings, plans and bible head lines.

Validators never raise on bad input; they return Violation records.
- severity hard: cannot be shown (parse errors, unknown speakers or drawn characters, weapons/gore/insults);
  soft: repair once, then substitution soft fixes, then accept with a log. An unknown delta id (`id.setup`) is
  soft and mechanical: soft_fix_page drops it and records `id.dropped`. LOG_ONLY codes are never a reason to
  repair; they stay on the page as residuals for the metrics.
- scope local: the line itself can be repaired; structural: needs pages that are not yet committed.
- Delta ids resolve as a bible setup or an item of the node's ledger (ideas, promises): resolve_id().
Messages are Chinese because they are pasted into repair prompts.
"""
from __future__ import annotations

import copy
import dataclasses
import re
from dataclasses import dataclass, field

from . import textutil as tu
from .content import Content
from .models import BiblePublic, Option, StoryState

HARD, SOFT = "hard", "soft"
LOCAL, STRUCT = "local", "structural"
OPTION_KINDS = ("careful", "bold", "silly")
META_WORDS = ("伏笔", "节拍", "钩子", "孩子的选择", "你选择了", "这个选择", "做出选择", "选项", "读者", "本章", "这一章",
              "提示词", "作为AI", "翻盘")         # 翻盘: our prompts' old word for the turn, never the child's
PASSIVE = re.compile(r"^(问问?|看看|看一看|瞧瞧|听听|听一听|想想|想一想|观察|等等|等一等|数一数)")
PERSUADE = re.compile(r"劝.{0,6}别")
SFX_FUNCTION = re.compile(r"[我你他她它的了吗呢是在有这那]")
QUOTED = re.compile(r"“[^”]*”|「[^」]*」|\"[^\"]*\"")               # quoted speech inside a line
NARR_PARTICLE = re.compile(r"(了|啦)?(咧|嘞)(?=[。！？!?…~～—]|$)")   # 熊二's sentence-final particles
JIJI_WO = re.compile(r"我(?![们俩])")                               # 吉吉国王 says 本王 (我们 is fine)
SOUND_PARTS = re.compile(r"[，,、。！？!?…—～~·\s]+")
NARR_QUESTION = re.compile(r"(呢|吗)[？?]$")
QUOTED_SPEECH = re.compile(r"[：:]\s*[“「][^”」]{2,}[”」]|[“「][^”」]*[！？。，!?][^”」]*[”」]")
GENERIC_Q = re.compile(r"^(该|要)?(怎么办|咋办)(呢)?[？?]?$")
QUESTION_END = ("吗", "呢", "么", "谁", "哪", "哪儿", "哪里", "啥", "怎么办", "怎么样", "咋办", "几", "何")   # 「…？」 alone
# the last clause asks (「谁来破这个局」, 「拿什么进屋找蜂蜜」): a question word not after 没/不/没有 and not before 也/都
# (谁也打不开, 什么都没找到) or 怕 (哪怕); 儿/里 keep 哪 from matching inside 哪儿也/哪里也; 几 also means "a few" (好几罐)
ASKS = re.compile(r"(?<!没有)(?<![没不])(谁|什么|啥|哪儿|哪里|哪|怎么|怎样|如何|为什么|咋|多少)(?![也都怕儿里])[^，,。！？!?；;]*$")
Q_TAIL = "，怎么办？"
HOWTO = re.compile(r"想.?办法|想.?主意|怎么办|咋办")       # a clause that only says 「find a way」 tells no situation
CLAUSE = re.compile(r"[，,；;、]")
SUDDEN = re.compile(r"就在这个时候|就在这时|这时候|突然|忽然")
VIRTUE = re.compile(r"夸|说真话|说实话|诚实|分享|帮助|善良|谢谢|礼貌")
# A rule about rules (r1 004 「天上每站都有一条怪规矩」, effect 「必须按规矩做才能发车」, limit 「每站一条」) made a new rule on every
# page; one cause → effect the child can predict is the rule (M3 r2 #7). 「每次有人打喷嚏…」 is one rule and passes, and so does
# the classifier 条 (「每个喷嚏都有一条彩虹」, 「每次只掉一条鱼」, 「每人一条围巾」): only 「每…一条」 with nothing after it is a count of rules.
RULE_META = re.compile(r"每[^，。！？；]{0,6}都有[^，。！？；]{0,4}(?:规矩|规定)|每[^，。！？；]{0,3}一条(?=[，。！？；]|$)"
                       r"|都有一条[^，。！？；]{0,3}规矩|各有[^，。！？；]{0,6}规矩|[按照]规矩|新规矩|规矩的规矩")
MANNER_BAD = re.compile(r"[“”「」\"]|必|每次|一定|总")
JOINED = re.compile(r"[、，,/；;_\s]+|和|与")         # 「damahou、ergou」, 「qiang_phone」: ids or names in one field
DECISION = re.compile(r"^[^：:]{1,10}决定[：:]")       # an idea option's frame, 「熊二决定：」
# A token is what a choice leaves behind: a thing, a place or a helper. An action token (r1: 捂耳朵, 推石头, 唱歌跑调)
# was re-enacted by later chapters and read back as 「得到了「捂耳朵」」 (M3 r2 #4): it opens with an action verb, maybe
# after an adverb (再抢口哨, 直接拿哨). Nouns that open with one of these characters are things (盖子, 跳绳, 飞天大沙发).
TOKEN_VERB = re.compile(r"^(?:再|又|先|还|快|直接|赶紧|一起)?([捂推唱吹抢拉找用打踩盖抹扔塞喊跳拿给请让把被掏抠揪缠换追交帮停招吐照粘套翻"
                        r"弹卡转飞])")
TOKEN_NOUNS = ("盖子", "盖头", "被子", "被窝", "被单", "拉链", "拉杆", "拉面", "跳绳", "跳板", "跳棋", "跳跳糖", "抹布", "把手",
               "吹风机", "唱片", "推车", "推土机", "打气筒", "请帖", "请柬", "塞子", "照片", "照相机", "套子", "用具", "交通",
               "弹簧", "弹珠", "卡车", "卡片", "转盘", "转椅", "飞机", "飞船", "飞碟", "飞毯", "飞天", "飞镖", "换洗")
AUX = frozenset("来去要想会能先再又还也都就快用给跟请让叫同")   # after an actor's name these are not the action
DELTA_LISTS = ("items_add", "items_remove", "flags", "plant", "payoff")
# The picture brief's texts that B1's image prompt can copy word for word (M3 r3 review, R3-SAFE-2): the brief's own
# and each drawn character's. All of them get the safety lists (_art_safety) and the fixed replacements (soft_fix_page).
ART_TEXT = ("focus", "place", "time", "weather", "shot", "mood")
WHO_TEXT = ("act", "face")
# residuals for the metrics; never repaired, never a reason to refuse a repair (M3 r2 review: fork.token_action, q.unseen,
# state.where measure round 2 — a fork keeps no residual record, tools/revalidate.py replays them)
LOG_ONLY = frozenset({"payoff.unplanted", "turn.unplanted", "fork.token_action", "q.unseen", "state.where"})
# fixed in code without a call (soft_fix_page); an unknown delta id (id.setup) is dropped, never repaired; a speaker
# missing from the picture goes offscreen (art.speaker); stray quotes at a line's ends are dropped (quote.unmatched)
MECHANICAL = frozenset({"voice.an", "voice.benwang", "voice.xionger_wo", "script.latin", "script.digit",
                        "script.emoji", "tierB", "sudden", "id.setup", "art.speaker", "quote.unmatched",
                        "safety.word", "adult.word",       # fixed replacements: 捂死 → 捂紧, 必定 → 一定 (M3 r2)
                        "voice.narr_an", "voice.jiji_wo", "say.empty", "narr.sfx",    # read-aloud slips (M3 r2 #16)
                        "narr.two"})                       # two sentences, two lines (M3 r2, findings #15)
# the lean writer's one repair (M3 r3 item 4): a safety hit, in the text or the picture brief; a hard one left after it
# drops the line. Everything else on a lean page is fixed in code (MECHANICAL, lean_fix_page) or kept as a residual.
LEAN_SAFETY = frozenset({"safety", "safety.soft", "safety.art"})
ASCII_ID = re.compile(r"^[A-Za-z0-9_\-]+$")        # an id, not a name a child could hear
REVEAL_STOP = ("其实", "根本", "原来", "只是", "一直", "本来")      # words of any truth: they tell none (left out like names)
# A child's idea set up to fail (M3 r2 #14, findings #6): r1 005 「光头强张开双臂，扑了个空。」「漏风啦，抱不住咯。」 and the hint
# 「可是…不能被抱住」. Ideas come true first; these words next to the idea on its first page, or in its 「conflict」, say it
# did not.
IDEA_FAILS = re.compile(r"扑了?个?空|落空|白费|失败|做不到|办不到|不能|没法|没办法|没(能|有)?(抱|拿|抓|够|追|拉|推|搬|举|接|挡|赶|捉|"
                        r"按|堵|拦|盖|关|摘|叫|喊|吹|游|跳|飞|爬|做|办|变|唱|哄)成|(抱|拿|抓|够|追|拉|推|搬|举|接|挡|赶|捉|按|堵|拦|盖|关|"
                        r"摘|叫|喊|吹|游|跳|飞|爬)不(住|到|动|着|上|走|开|响|醒|下|起|了)")
CARD_ROWS = 5.5         # the card holds five lines incl. one 56 px sfx row (5.2) at 46 px; past this it overflows
OVER_LINES, OVER_ROWS = 6, 6.5      # past these a page is split in two after its repair (`over`: M3 r2, findings #15)
PROBLEMS = {"safety": "不适合小朋友的词", "safety.soft": "小朋友可能模仿的危险行为", "script.latin": "英文字母",
            "script.digit": "阿拉伯数字", "script.emoji": "表情符号", "meta": "故事外的词", "tierA": "套话",
            "adult": "大人才用的词"}


@dataclass
class Violation:
    """where: "page", "art", "delta", "line:<i>" (0-based), "line:first", "q", "opts", "opts:<i>", "ideas",
    "choice" (parse/schema/safety/cast problems of a whole fork line), "chapter", "end", "plan", "world", "setups",
    "secret" or "title"."""
    code: str
    severity: str
    scope: str
    where: str
    message: str
    data: dict = field(default_factory=dict)


@dataclass
class PageCtx:
    content: Content
    bible: BiblePublic
    state: StoryState
    chapter: int
    page_in_chapter: int
    pages_in_chapter: int
    is_final_chapter: bool
    chosen: Option | None = None
    turn_allowed: bool = False
    memory_phrases: frozenset = frozenset()
    copy_sources: tuple = ()
    removed_items: tuple = ()
    ledger: tuple = ()                  # LedgerItem objects of the node: ids of ideas/promises resolve here
    first_page: tuple = ()              # the texts of the book's page 1 lines: the last page may not copy two (echo.copy)
    line: tuple = ()                    # the texts of the world line's pages before this one (state.where)

    @property
    def is_first_page(self) -> bool:
        return self.page_in_chapter == 1

    @property
    def is_last_page(self) -> bool:
        return self.is_final_chapter and self.page_in_chapter == self.pages_in_chapter

    @property
    def turn_setup_id(self) -> str:
        t = self.bible.turn_setup()
        return str(t.get("id", "")) if t else ""


@dataclass
class ForkCtx:
    content: Content
    bible: BiblePublic
    state: StoryState
    fork_index: int
    is_final_fork: bool
    page_text: str = ""             # the world line's pages so far: a name they carry is no news on the fork
    present: tuple = ()             # who is on the last page (its picture, its speakers): nobody fetches them


@dataclass
class ChapterCheck:
    content: Content
    bible: BiblePublic
    due_payoffs: tuple = ()
    must_plant: tuple = ()
    token: str = ""
    is_finale: bool = False
    needs_rule: bool = False
    ledger: tuple = ()
    option_text: str = ""           # the chosen option as the child saw it: its words in the chapter carry the token too
    reveal: str = ""                # the truth this chapter tells (plan.reveal): its words must be in the text


class _Acc(list):
    def add(self, code, severity, where, message, scope=LOCAL, **data):
        self.append(Violation(code, severity, scope, where, message, data))


def hard(vs: list[Violation]) -> list[Violation]:
    return [v for v in vs if v.severity == HARD]


def codes(vs: list[Violation]) -> list[str]:
    return sorted({v.code for v in vs})


def _list(x) -> list:
    return x if isinstance(x, list) else []


def first_str(x) -> str:
    """A model's text field as it is shown or quoted: a string as it is, a list's first string (a model may write ["…"]
    for one field, as freetext.story_phrase reads it), anything else "" — never its repr: q None shipped as 'None' and a
    list as "['…']" (M3 r3 review, R3-ROB-3)."""
    if isinstance(x, list):
        x = next((y for y in x if isinstance(y, str)), "")
    return x if isinstance(x, str) else ""


def as_list(x) -> list:
    """A delta list field as a list: a model may write "plant": "S2" instead of ["S2"]; never iterate a string per
    character. Blank strings and other shapes (null, numbers, objects) are empty."""
    if isinstance(x, str):
        return [x] if x.strip() else []
    return list(x) if isinstance(x, list) else []


def _ledger_item(ledger, sid):
    return next((x for x in (ledger or ()) if getattr(x, "id", None) == sid), None)


def resolve_id(bible: BiblePublic | None, ledger, sid) -> dict | None:
    """A delta id as {id, what, role, kind}: a bible setup first, else an item of the node's ledger (idea and promise
    items have no bible entry). None when it is neither: the id is unknown and gets dropped."""
    if not isinstance(sid, str) or not sid:
        return None
    s = bible.setup(sid) if bible is not None else None
    if s is not None:
        return {"id": sid, "what": str(s.get("what", "")), "role": str(s.get("role", "")), "kind": "setup"}
    item = _ledger_item(ledger, sid)
    if item is not None:
        return {"id": sid, "what": str(item.what or ""), "role": str(item.role or ""), "kind": str(item.kind or "")}
    return None


def _cast(ctx) -> set[str]:
    """The world line's cast: the bible's plus cameo characters an idea brought in (state.cast_extra)."""
    return {x for x in list(ctx.bible.cast) + list(ctx.state.cast_extra) if isinstance(x, str)}


def _lines(obj) -> list:
    lines = obj.get("lines") if isinstance(obj, dict) else None
    return lines if isinstance(lines, list) else []


def _text(lines) -> str:
    return "".join(l["text"] for l in lines if isinstance(l, dict) and isinstance(l.get("text"), str))


def _art_text(obj) -> str:
    art = obj.get("art") if isinstance(obj.get("art"), dict) else {}
    who = [w for w in _list(art.get("who")) if isinstance(w, dict)]
    return str(art.get("focus", "")) + "".join(str(w.get("act", "")) for w in who)


def _art_parts(obj) -> list[str]:
    """The picture brief's words, apart: every text of it the image prompt can copy — art.focus, place, time, weather,
    shot and mood, each who.act and who.face (strings only; M3 r3 review R3-SAFE-2: 「满脸鲜血」 in a face, 「特写匕首」 in
    the shot reached B1's image prompt unchecked)."""
    art = obj.get("art") if isinstance(obj, dict) and isinstance(obj.get("art"), dict) else {}
    who = [w for w in _list(art.get("who")) if isinstance(w, dict)]
    parts = [art.get(k) for k in ART_TEXT] + [w.get(k) for w in who for k in WHO_TEXT]
    return [s for s in parts if isinstance(s, str) and s.strip()]


def _people(content: Content, bible: BiblePublic) -> list[tuple[str, ...]]:
    """Each character's names as the text writes them: every canon character (aliases too: 光头强/强哥) and the guest."""
    out = [tuple(content.names(cid)) for cid in list(content.characters) + list(content.minor)]
    guest = bible.guest.get("name") if bible.has_guest() else ""
    if isinstance(guest, str) and guest:                       # a malformed or old bible never breaks a check
        out.append((guest,))
    return [x for x in out if x]


def _names(content: Content, bible: BiblePublic) -> list[str]:
    """Names that are never content words: every character's names, the guest's and the places."""
    places = [p for p in bible.places if isinstance(p, str) and p] if isinstance(bible.places, list) else []
    return [n for group in _people(content, bible) for n in group] + places


def _hits(patterns, text) -> list[str]:
    """The patterns' hits (the first of each) in the text and in its folded copy (textutil.fold: 「大——笨——蛋！」 is read
    as 「大笨蛋！」 too, M3 r3 review R3-SAFE-1) — every list check (safety, the picture brief, display strings) goes
    through here."""
    texts = {text, tu.fold(text)}
    return sorted({m.group(0) for p in patterns for t in texts for m in [p.search(t)] if m})


def _count_any(text: str, words) -> int:
    """Non-overlapping hits of any of the words, longest first (so 轻轻地 is not also counted as 轻轻)."""
    ws = sorted({w for w in words if w}, key=len, reverse=True)
    return len(re.findall("|".join(map(re.escape, ws)), text)) if ws else 0


def _subs(content: Content, key: str) -> dict:
    """The fixed replacements of a phrases.json list ("safety", "adult"): {word: replacement}."""
    d = content.phrases.get(key, {}).get("substitutions", {}) if isinstance(content.phrases.get(key), dict) else {}
    return {k: v for k, v in d.items() if isinstance(k, str) and k and isinstance(v, str)} if isinstance(d, dict) else {}


def swap_words(s: str, content: Content, key: str | None = None) -> str:
    """`s` with the fixed replacements of the safety and adult lists made (or of one list), longest first: 捂死 → 捂紧,
    死死 dropped, 必定 → 一定, 在场的人 → 大家 (M3 r2 findings #4, #15; M3 r3 lean #1). Mechanical, never a repair call."""
    subs = _subs(content, key) if key else {**_subs(content, "safety"), **_subs(content, "adult")}
    for old in sorted(subs, key=len, reverse=True):
        s = s.replace(old, subs[old])
    return s


def _swaps(text: str, content: Content, key: str) -> list[str]:
    return sorted(w for w in _subs(content, key) if w in text)


def _adult(text: str, content: Content) -> list[str]:
    """The adult list's words in `text` (M3 r2 #15), once its fixed replacements (在场的人 is swapped, a bare 在场 is
    repaired) and its false friends (在场地上) are taken out."""
    adult = content.phrases.get("adult") if isinstance(content.phrases.get("adult"), dict) else {}
    friends = [w for w in adult.get("false_friends", []) if isinstance(w, str) and w]
    for w in sorted(list(_subs(content, "adult")) + friends, key=len, reverse=True):
        text = text.replace(w, "|")
    words = adult.get("words", [])
    return sorted({w for w in words if isinstance(w, str) and w and w in text})


def normalize_page(obj: dict) -> dict:
    """Quote normalisation, whitespace cleanup and delta list fields as lists (never changes meaning)."""
    o = copy.deepcopy(obj)
    for l in _lines(o):
        if isinstance(l, dict) and isinstance(l.get("text"), str):
            t = tu.normalize_quotes(l["text"].strip())
            if l.get("k") == "say":
                t = tu.strip_outer_quotes(t)
            l["text"] = t
    d = o.get("delta") if isinstance(o, dict) else None
    if isinstance(d, dict):
        for k in DELTA_LISTS:
            if k in d:
                d[k] = as_list(d[k])
    return o


# ---------------------------------------------------------------- pages
def validate_page(obj: dict, ctx: PageCtx) -> list[Violation]:
    v = _Acc()
    if not isinstance(obj, dict) or "__parse_error__" in obj:
        v.add("parse", HARD, "page", "这一行不是合法的 JSON，请按格式重写这一页。")
        return v
    if obj.get("type") != "page":
        v.add("schema.type", HARD, "page", "这一行的 type 必须是 page。")
        return v
    lines = _lines(obj)
    if not lines:
        v.add("schema.lines", HARD, "page", "lines 不能为空。")
        return v
    c, b = ctx.content, ctx.bible
    guest = b.guest.get("name", "") if b.has_guest() else ""
    speakers_ok = _cast(ctx) | set(c.minor) | ({"guest"} if guest else set())
    rows, total = [], 0
    for i, l in enumerate(lines):
        where = f"line:{i}"
        if (not isinstance(l, dict) or l.get("k") not in ("narr", "say", "sfx")
                or not isinstance(l.get("text"), str) or not l["text"].strip()):
            v.add("schema.line", HARD, where, f"第{i + 1}行格式不对：k 必须是 narr、say 或 sfx，text 不能为空。")
            continue
        k, text = l["k"], l["text"]
        total += tu.cjk_len(text)
        name = None
        if k == "say":
            who = l.get("who")
            if not isinstance(who, str) or who not in speakers_ok:
                v.add("id.speaker", HARD, where, f"第{i + 1}行的说话人「{who}」不在本书角色表里；客串角色请写 guest。")
            name = c.display_name(who, guest) if isinstance(who, str) else "某人"
        if k == "sfx":
            if tu.cjk_len(text) > 6:
                v.add("sfx.len", SOFT, where, f"第{i + 1}行的拟声词太长了，最多六个字。")
            if SFX_FUNCTION.search(text):
                v.add("sfx.speech", SOFT, where, f"第{i + 1}行不是拟声词；会说话的东西请写成 say 行（客串角色用 guest）。")
        if k == "narr" and QUOTED_SPEECH.search(text):
            v.add("narr.dialogue", SOFT, where, f"第{i + 1}行把台词写进了旁白，请把台词单独写成一个 say 行。")
        for sent in tu.split_sentences(text):
            n = tu.cjk_len(sent)
            if n > 25:
                v.add("len.sentence", SOFT, where, f"第{i + 1}行有一句{n}个字，太长了，请拆成短句。", over_hard_limit=n > 40)
        if tu.has_latin(text):
            v.add("script.latin", SOFT, where, f"第{i + 1}行出现了英文字母，请改成中文。")
        if tu.has_digit(text):
            v.add("script.digit", SOFT, where, f"第{i + 1}行出现了阿拉伯数字，请写成汉字。")
        if tu.has_emoji(text):
            v.add("script.emoji", SOFT, where, f"第{i + 1}行出现了表情符号，请删掉。")
        if tu.drop_stray_quotes(text) != text.strip():
            v.add("quote.unmatched", SOFT, where, f"第{i + 1}行的引号不成对，请删掉多出来的引号。")
        rows.append((k, text, name))
    if not 2 <= len(lines) <= 5:
        v.add("len.lines", SOFT, "page", f"这一页有{len(lines)}行，请写成二到五行。", over=len(lines) > OVER_LINES)
    if not 20 <= total <= 80:
        v.add("len.page", SOFT, "page", f"这一页有{total}个字，请控制在二十到八十个字。")
    r = tu.card_rows(rows)
    if r > CARD_ROWS:
        v.add("len.card", SOFT, "page", f"这一页的文字框放不下（需要{r}行，最多五行），请写短一些。", over=r > OVER_ROWS)
    for i in _two_sentence_lines(lines, ctx):
        v.add("narr.two", SOFT, f"line:{i}", f"第{i + 1}行有两句话，请拆成两行。")
    v += _voice(lines, ctx)
    v += _sounds(lines, ctx)
    v += _phrases(lines, ctx)
    v += _outside(lines, ctx)
    v += _art(obj, lines, ctx)
    v += _delta(obj, lines, ctx)
    v += _where(lines, ctx)
    if ctx.is_first_page and ctx.chosen is not None:
        v += _ack(obj, lines, ctx)
    v += _safety(_text(lines), c, "page")
    v += _art_safety(obj, c)
    if ctx.is_last_page and ctx.first_page:
        v += _echo(lines, ctx)
    if ctx.copy_sources:
        spans = tu.copied_spans(_text(lines), ctx.copy_sources)
        if spans:
            v.add("copy", SOFT, "page", "请不要照搬现成的句子「" + "、".join(spans) + "」，用自己的话写。", spans=spans)
    return v


def narr_voice(text: str, an: str = "熊二") -> str:
    """A narration line without 熊二's voice outside its quotes (M3 r2 #16): 俺 → 熊二, or 他 once 熊二 is named before it
    in the line; 俺们 → 大家; a sentence-final 咧 → 了, 嘞 → 啦 (r1 001 「…硌着俺。」, 「…雾哨鸟闭眼睡着咧。」). Quoted speech
    keeps its words; 咧嘴 is no particle. `an` is the name of the one who says 俺."""
    out, pos = "", 0
    for m in list(QUOTED.finditer(text)) + [None]:
        seg = text[pos:m.start()] if m else text[pos:]
        seg = NARR_PARTICLE.sub(lambda x: x.group(1) or ("了" if x.group(2) == "咧" else "啦"), seg).replace("俺们", "大家")
        for ch in seg:
            out += ("他" if an in out else an) if ch == "俺" else ch
        if m:
            out, pos = out + m.group(0), m.end()
    return out


def _card(lines, ctx) -> float:
    """The card rows of page lines (dicts), speakers by their display names."""
    guest = _guest_name(ctx.bible)
    return tu.card_rows([(l.get("k"), str(l.get("text", "")),
                          ctx.content.display_name(l["who"], guest) if l.get("k") == "say" and isinstance(l.get("who"), str)
                          else None) for l in lines if isinstance(l, dict)])


def _two_sentences(text: str) -> list[str]:
    """A narration line of exactly two sentences ended by 。, each of three 字 or more, no quotes: its two halves."""
    parts = [p for p in re.split(r"(?<=。)", text or "") if p.strip()]
    if len(parts) != 2 or QUOTED.search(text) or any(tu.cjk_len(p) < 3 for p in parts):
        return []
    return [p.strip() for p in parts]


def _two_sentence_lines(lines, ctx) -> list[int]:
    """Narration lines of two sentences that become two lines (narr.two, in code: r1 005 「三人蹚水逃出小木屋。挂钟敲第四下。」 left
    no pause before the countdown) while the page stays under six lines and on the card, first come first."""
    if not all(isinstance(l, dict) for l in lines) or len(lines) >= 5:
        return []
    out, n = [], len(lines)
    for i, l in enumerate(lines):
        halves = _two_sentences(l["text"]) if l.get("k") == "narr" and isinstance(l.get("text"), str) else []
        if halves and n + 1 <= 5:
            trial = [x for j, ln in enumerate(lines) for x in ([{"k": "narr", "text": h} for h in _two_sentences(ln["text"])]
                                                                 if j in out + [i] else [ln])]
            if _card(trial, ctx) <= CARD_ROWS:
                out.append(i)
                n += 1
    return out


def split_page(obj: dict, ctx) -> tuple | None:
    """An overlong page (`over`) as two pages, cut between lines at the most even place where both halves fit (≤ 5 lines,
    on the card), else the most even cut; a page of one line is cut between its sentences, and None when there is no
    boundary. Both halves keep the picture; the delta stays with the first half except a plant or payoff whose thing is
    named only in the second (M3 r2, findings #15: never ship a 7-line page)."""
    lines = [dict(l) for l in _lines(obj) if isinstance(l, dict)]
    if len(lines) < 2:
        lines = [dict(lines[0], text=t) for t in tu.split_sentences(lines[0].get("text", ""))] if lines else []
    if len(lines) < 2:
        return None
    best = None
    for cut in range(1, len(lines)):
        a, b = lines[:cut], lines[cut:]
        ra, rb = _card(a, ctx), _card(b, ctx)
        fits = len(a) <= 5 and len(b) <= 5 and ra <= CARD_ROWS and rb <= CARD_ROWS
        key = (not fits, max(ra, rb), abs(len(a) - len(b)))
        if best is None or key < best[0]:
            best = (key, cut)
    a, b = lines[:best[1]], lines[best[1]:]
    d = obj.get("delta") if isinstance(obj.get("delta"), dict) else {}
    fc = ctx.content.function_chars()
    ga, gb = tu.content_bigrams(_text(a), function_chars=fc), tu.content_bigrams(_text(b), function_chars=fc)
    moved: dict = {"plant": [], "payoff": []}
    for key in moved:
        for sid in as_list(d.get(key)):
            s = resolve_id(ctx.bible, ctx.ledger, sid)
            g = (tu.content_bigrams(head_noun(s["what"]), function_chars=fc) or
                 tu.content_bigrams(s["what"], function_chars=fc)) if s else set()
            if g and not g & ga and g & gb:
                moved[key].append(sid)
    first = dict(copy.deepcopy(obj), lines=a)
    first["delta"] = dict(copy.deepcopy(d), **{k: [x for x in as_list(d.get(k)) if x not in moved[k]] for k in moved})
    second = dict(copy.deepcopy(obj), lines=b, delta={"items_add": [], "items_remove": [], "flags": [], "rule_used": False,
                                                       "plant": moved["plant"], "payoff": moved["payoff"]})
    for o in (first, second):
        o.pop("_meta", None)
    return first, second


def _voice(lines, ctx) -> list[Violation]:
    v = _Acc()
    c = ctx.content
    anmen = ctx.state.count("xiongda_anmen")
    for i, l in enumerate(lines):
        if not isinstance(l, dict) or not isinstance(l.get("text"), str):
            continue
        if l.get("k") == "narr" and narr_voice(l["text"], c.name("xionger")) != l["text"]:
            v.add("voice.narr_an", SOFT, f"line:{i}", f"第{i + 1}行是旁白：旁白不说“俺”，也不用“咧”“嘞”结尾，那是熊二的口气。")
        if l.get("k") != "say":
            continue
        who, text, where = l.get("who"), l["text"], f"line:{i}"
        if not tu.cjk_len(text):               # r1 002 「发光石头：“……”」: an awkward silence read aloud
            v.add("say.empty", SOFT, where, f"第{i + 1}行的台词一个字也没有；没有话说，就写成一句旁白。")
            continue
        if not isinstance(who, str):
            continue
        if who == "jiji" and JIJI_WO.search(text) and "本王" not in text:     # r1 002 「我的香蕉！」
            v.add("voice.jiji_wo", SOFT, where, f"第{i + 1}行：吉吉国王自称“本王”，不说“我”。")
        if "俺" in text and who != "xionger":
            only_anmen = text.count("俺") == text.count("俺们")
            if who == "xiongda" and only_anmen and anmen < 1:
                anmen += 1
            else:
                v.add("voice.an", SOFT, where, f"第{i + 1}行：只有熊二自称“俺”，{c.name(who)}要说“我”。")
        if "本王" in text and who != "jiji":
            v.add("voice.benwang", SOFT, where, f"第{i + 1}行：只有吉吉国王自称“本王”。")
        if who == "xionger" and "我" in text and "俺" not in text:
            v.add("voice.xionger_wo", SOFT, where, f"第{i + 1}行：熊二要自称“俺”，不说“我”。")
        if who in c.characters:
            for tic in c.tics(who):
                core = tu.cjk_only(tic["text"])
                if core and core in tu.cjk_only(text) and ctx.state.count("tic:" + core) >= int(tic["max_per_book"]):
                    v.add("voice.tic", SOFT, where, f"第{i + 1}行：「{tic['text']}」这本书里已经用够了，换个说法。", tic=core)
    return v


def _rare(ch: str) -> bool:
    """A character outside GB2312 level 1 (嗄): parents stumble on it, the sfx font may lack it."""
    try:
        b = ch.encode("gb2312")
    except UnicodeEncodeError:
        return True
    return not 0xB0 <= b[0] <= 0xD7


def sound_like(text: str, sounds: str) -> bool:
    """A line made of short exclamations (one or two characters each, six at most) with a sound among them and no
    function word: 「叮！变！」, 「咚——」; not 「转圈停啦！」 or 「快！快！」."""
    parts = [p for p in SOUND_PARTS.split(text or "") if p]
    return (bool(parts) and all(1 <= len(p) <= 2 and tu.cjk_len(p) == len(p) for p in parts)
            and tu.cjk_len(text) <= 6 and any(ch in sounds for p in parts for ch in p) and not SFX_FUNCTION.search(text))


def _sounds(lines, ctx) -> list[Violation]:
    """sfx lines that are no sound (sfx.word: r1 「轻响——」「舔——」「弹——」, the rare 「嘎嗄！」; the book's refrain is exempt) and
    narration lines that are one (narr.sfx: r1 005 「叮！变！」)."""
    v = _Acc()
    sounds = str(ctx.content.phrases.get("sfx_chars", ""))
    refrain = tu.cjk_only(ctx.bible.refrain if isinstance(ctx.bible.refrain, str) else "")
    if not sounds:
        return v
    for i, l in enumerate(lines):
        if not isinstance(l, dict) or not isinstance(l.get("text"), str):
            continue
        text, chars = l["text"], tu.cjk_only(l["text"])
        if l.get("k") == "sfx" and not (chars and refrain and chars in refrain):
            bad = [ch for ch in chars if ch not in sounds]
            if not chars or 2 * len(bad) > len(chars) or any(_rare(ch) for ch in bad):
                v.add("sfx.word", SOFT, f"line:{i}", f"第{i + 1}行的拟声词「{text}」不是一个声音；请换成真的拟声词（比如咚、哗啦、叮当），"
                                                     "或者写成一句旁白。")
        elif l.get("k") == "narr" and sound_like(text, sounds):
            v.add("narr.sfx", SOFT, f"line:{i}", f"第{i + 1}行「{text}」是一个声音，请写成 sfx 行。")
    return v


def _guest_name(bible: BiblePublic) -> str:
    g = bible.guest.get("name") if bible.has_guest() else ""
    return g if isinstance(g, str) else ""


def mentions(content: Content, bible: BiblePublic, cid: str, text: str) -> bool:
    """The text names the canon character cid (its name or an alias), once the guest's name and the places are taken
    out (a place may carry a name: 光头强的小木屋) and then the character's false friends (毛毛虫 is not 毛毛)."""
    places = [p for p in bible.places if isinstance(p, str)] if isinstance(bible.places, list) else []
    for w in sorted({w for w in [_guest_name(bible)] + places if w}, key=len, reverse=True):
        text = text.replace(w, "|")
    for w in sorted(content.false_friends(cid), key=len, reverse=True):
        text = text.replace(w, "|")
    return any(n in text for n in content.names(cid))


def _off_line(ctx, text: str) -> list[str]:
    """Canon main-cast characters the text names while not on this world line (bible.cast and cameos). Minor
    characters (李老板 on the phone, 洞洞幺) are not main cast."""
    c, cast = ctx.content, _cast(ctx)
    return [cid for cid in c.characters if cid not in cast and mentions(c, ctx.bible, cid, text)]


def _our_cast(ctx) -> str:
    """Who a cast.outside message offers instead: 「（赵琳、熊二、光头强）或客串角色「雪兔」」."""
    b, guest = ctx.bible, _guest_name(ctx.bible)
    ours = list(dict.fromkeys(x for x in list(b.cast) + list(ctx.state.cast_extra) if isinstance(x, str)))
    return f"（{'、'.join(ctx.content.name(x) for x in ours)}）" + (f"或客串角色「{guest}」" if guest else "")


def _outside(lines, ctx) -> list[Violation]:
    """Canon main-cast characters named in the page text while not on this world line: 天才威 walking in through
    narration with his lines written as guest."""
    v = _Acc()
    out = _off_line(ctx, _text(lines))
    if out:
        v.add("cast.outside", SOFT, "page", f"{'、'.join(ctx.content.name(x) for x in out)} 不在这本书的角色里，请换成本书的角色"
                                            f"{_our_cast(ctx)}。", who=out)
    return v


def _phrases(lines, ctx) -> list[Violation]:
    v = _Acc()
    c = ctx.content
    tier_a = c.tier_a()
    for i, l in enumerate(lines):
        if not isinstance(l, dict) or not isinstance(l.get("text"), str):
            continue
        text, where = l["text"], f"line:{i}"
        if l.get("k") == "narr" or ctx.is_last_page:
            hits = _hits(tier_a, text)
            if hits:
                v.add("tierA", SOFT, where, f"第{i + 1}行用了套话「{'、'.join(hits)}」，请换成具体的动作或画面。", hits=hits)
        if l.get("k") != "narr":
            meta = [w for w in META_WORDS if w in text]
            if meta:
                v.add("meta", SOFT, where, f"第{i + 1}行出现了故事外的词「{'、'.join(meta)}」，请删掉。", hits=meta)
        grown = _adult(text, c)
        if grown:
            v.add("adult", SOFT, where, f"第{i + 1}行用了大人才用的词「{'、'.join(grown)}」，请换成四到十岁孩子听得懂的说法。",
                  hits=grown)
        swaps = _swaps(text, c, "adult")
        if swaps:
            v.add("adult.word", SOFT, where, f"第{i + 1}行的「{'、'.join(swaps)}」是大人的说法，换成孩子的说法。", hits=swaps)
    page = _text(lines)
    for g in c.tier_b():
        n = _count_any(page, g["variants"])
        if not n:
            continue
        budget = 0 if any(x in ctx.memory_phrases for x in g["variants"]) else g["max_per_book"]
        if ctx.state.count("tierb:" + g["key"]) + n > budget:
            v.add("tierB", SOFT, "page", f"「{g['key']}」这本书里用得太多了，换个说法。", key=g["key"], variants=g["variants"])
    ns = len(SUDDEN.findall(page))
    limit = int(c.phrases.get("sudden", {}).get("max_per_chapter", 1))
    if ns and ctx.state.count(f"sudden:{ctx.chapter}") + ns > limit:
        v.add("sudden", SOFT, "page", "“突然”“忽然”“就在这时”一章最多用一次。")
    first = lines[0] if isinstance(lines[0], dict) else {}
    if first.get("k") == "narr" and c.opening_banned().search(str(first.get("text", ""))):
        v.add("opening", SOFT, "line:0", "不要用时间加风景开头（比如“清晨的狗熊岭……”），请用动作、声音或台词开头。")
    nq = sum(1 for l in lines if isinstance(l, dict) and l.get("k") == "narr"
             and NARR_QUESTION.search(str(l.get("text", "")).strip()))
    if nq and ctx.state.count("narr_q") + nq > int(c.phrases.get("narr_question_max_per_book", 2)):
        v.add("narr_question", SOFT, "page", "旁白提问太多了，请把结尾改成一个具体的动作或悬念。")
    return v


def _unseen_speakers(art: dict, lines) -> list[str]:
    """Speakers (in order) neither drawn (art.who) nor listed in art.offscreen; 李老板 is only ever on the phone."""
    seen = {w.get("id") for w in _list(art.get("who")) if isinstance(w, dict) and isinstance(w.get("id"), str)}
    seen |= {x for x in _list(art.get("offscreen")) if isinstance(x, str)} | {"libanban"}
    said = [l.get("who") for l in lines if isinstance(l, dict) and l.get("k") == "say" and isinstance(l.get("who"), str)]
    return [x for x in dict.fromkeys(said) if x not in seen]


def _art(obj, lines, ctx) -> list[Violation]:
    v = _Acc()
    art = obj.get("art")
    if not isinstance(art, dict):
        v.add("art.missing", SOFT, "art", "缺少 art 画面说明。")
        return v
    b = ctx.bible
    ok_ids = _cast(ctx) | ({"guest"} if b.has_guest() else set()) | {"dongdongyao"}
    who = [w for w in _list(art.get("who")) if isinstance(w, dict)]
    if len(who) > 3:
        v.add("art.who_count", SOFT, "art", "画面里最多三个角色。")
    for w in who:
        if w.get("id") == "libanban":
            v.add("art.libanban", SOFT, "art", "李老板只在电话里出现，不能画进画面；请把他放进 offscreen。")
        elif not isinstance(w.get("id"), str) or w.get("id") not in ok_ids:
            v.add("id.art", HARD, "art", f"art.who 里的「{w.get('id')}」不是本书角色；客串角色请写 guest。")
    missing = _unseen_speakers(art, lines)
    if missing:
        v.add("art.speaker", SOFT, "art", "说话的角色要么画在 who 里，要么写进 offscreen：" + "、".join(sorted(missing)) + "。")
    if not str(art.get("focus", "")).strip():
        v.add("art.focus", SOFT, "art", "请写出 art.focus：这一页画面最重要的东西或动作。")
    return v


def head_noun(what) -> str:
    """The thing a setup plants: the part of `what` after its last 的 (松果权杖底座里藏着的备用松果 → 备用松果), else its
    last four CJK characters (半块蜂蜜饼 → 块蜂蜜饼); the whole `what` when that leaves fewer than two."""
    w = str(what or "")
    head = tu.cjk_only(w.rsplit("的", 1)[1]) if "的" in w else tu.cjk_only(w)[-4:]
    return head if len(head) >= 2 else w


def clue_shown(content: Content, bible: BiblePublic | None, clue: str, text: str) -> bool:
    """The twist's clue is in `text`: two of its content bigrams, or its head noun (a clue with a 的), every name, the
    guest and the places taken out. One shared bigram, a name or a place is no clue — r1 004 n.p2 shared only the guest's
    name and 「说话」 with 「云站牌说话像李老板的大嗓门」 (findings #7 fix 4, the review's tests-twist-clue-count-lax)."""
    clue = str(clue or "")
    names = _names(content, bible) if bible is not None else []
    fc = content.function_chars()
    cg = tu.content_bigrams(clue, remove=names, function_chars=fc)
    head = tu.cjk_only(clue.rsplit("的", 1)[1]) if "的" in clue else ""      # a head of one character is none
    hg = tu.content_bigrams(head, remove=names, function_chars=fc) if len(head) >= 2 else set()
    tg = tu.content_bigrams(text or "", remove=names, function_chars=fc)
    return len(cg & tg) >= 2 or bool(hg & tg)


def thing_name(what) -> str:
    """The name of the thing a setup plants: a bare what (no 的, six 字 at most: the bible's wording since M3 r2 #12,
    「半块蜂蜜饼」) as it is, else its head noun (「吉吉国王常带在身边的松果权杖」 → 松果权杖)."""
    w = str(what or "").strip()
    return w if "的" not in w and 2 <= tu.cjk_len(w) <= 6 else head_noun(w)


# A thing the line broke, lost or turned into something else (state.where, log-only: M3 r2 review, findings #8 fix 5), and
# what brings one back on the page that names it again.
GONE = re.compile(r"碎|飞走|飘走|没了|不见了|丢了|弄丢|吃光|吃掉|烧了|化了")
TURNED = "变成"
TURNED_NEXT = re.compile(r"(就|又|一下子|立刻|马上|全)?变成")      # 「…，变成…」: the next clause turns it
BACK = re.compile(r"找回|捡回|拿回|要回|抢回|修好|补好|粘好|变回|长回|又有了")
_CLAUSES = re.compile(r"[，,。！？!?；;：:…—]+")


def _line_things(ctx) -> list[str]:
    """The things this world line knows: its items (held or lost; a setup id written as an item is its thing) and the
    setups and ideas of its ledger that are no longer only planned."""
    out = []
    for x in list(ctx.state.items) + list(ctx.state.removed):
        s = resolve_id(ctx.bible, ctx.ledger, x.strip()) if isinstance(x, str) else None
        out.append(thing_name(s["what"]) if s and s.get("what") else re.sub(r"[（(].*?[）)]", "", str(x)).strip())
    out += [thing_name(x.what) for x in ctx.ledger if getattr(x, "status", "") != "planned" and getattr(x, "what", "")]
    return [t for t in dict.fromkeys(out) if tu.cjk_len(t) >= 2]


def _last_said(line, thing: str) -> tuple[str, str]:
    """(the line's last sentence naming the thing, what it says of it): "gone" when the thing's clause says it broke, flew
    off, was lost or eaten, or when it turns into something — it opens its clause (or follows 把) and 变成 comes after it
    or opens the next clause: 「背心撞上鲱鱼罐头，变成冒臭气的铁皮筒」 turns the 背心, not the 鲱鱼罐头 —, "same" when what it
    turns into is named after it (松果 → 松果礼服: a later 松果 may be that), else "here"; ("", "") when no sentence names it."""
    for t in reversed([x for x in line if isinstance(x, str)]):
        for sent in reversed(tu.split_sentences(t)):
            parts = [c for c in _CLAUSES.split(sent) if c]
            idx = [i for i, c in enumerate(parts) if thing in c]
            if not idx:
                continue
            i, c = idx[-1], parts[idx[-1]]
            nxt = parts[i + 1] if i + 1 < len(parts) else ""
            turns = c.lstrip("又也还就").startswith(thing) or f"把{thing}" in c       # the one that turns, not what it
            into = (c.split(TURNED, 1)[1] if turns and TURNED in c and c.find(thing) < c.find(TURNED)   # bumped into
                    else nxt.split(TURNED, 1)[1] if turns and TURNED_NEXT.match(nxt) else None)
            if into is not None:
                return sent, "same" if thing in into else "gone"
            return sent, "gone" if GONE.search(c) else "here"
    return "", ""


def _where(lines, ctx) -> list[Violation]:
    """state.where (log-only): the page names a thing of the line, whole, while the line's last sentence naming it said
    it broke, flew off, was lost or turned into something, and nothing on the page brings it back (r1 003: 「树洞撇下碎
    海螺」 on n.B.p3, then 「海螺从包里滚出来，落在沙滩上。」 on n.B.C.A.p3)."""
    v = _Acc()
    page = _text(lines)
    if not ctx.line or BACK.search(page):
        return v
    hits = []
    for thing in _line_things(ctx):
        here = [c for c in _CLAUSES.split(page) if thing in c]
        if not here or all(GONE.search(c) for c in here):          # not named, or named as still broken
            continue
        sent, said = _last_said(ctx.line, thing)
        if said == "gone":
            hits.append((thing, sent))
    if hits:
        v.add("state.where", SOFT, "page", "；".join(f"「{t}」前面已经「{c}」" for t, c in hits)
              + "：要让它再出现，得先写清楚它是怎么回来的。", things=[t for t, _ in hits])
    return v


def _delta(obj, lines, ctx) -> list[Violation]:
    v = _Acc()
    d = obj.get("delta") if isinstance(obj.get("delta"), dict) else {}
    fc = ctx.content.function_chars()
    text_g = tu.content_bigrams(_text(lines), function_chars=fc)
    art_g = tu.content_bigrams(_art_text(obj), function_chars=fc)
    plants = as_list(d.get("plant"))
    for key in ("plant", "payoff"):
        for sid in as_list(d.get(key)):
            s = resolve_id(ctx.bible, ctx.ledger, sid)
            if s is None:
                v.add("id.setup", SOFT, "delta", f"delta.{key} 里的「{sid}」不是本书的伏笔编号，请删掉它。", key=key, sid=sid)
                continue
            g = tu.content_bigrams(s.get("what", ""), function_chars=fc)
            if key == "plant" and g:
                head = head_noun(s.get("what", ""))             # the thing itself, not its container or owner
                if not (tu.content_bigrams(head, function_chars=fc) or g) & text_g:
                    v.add("plant.text", SOFT, "page", f"埋下伏笔 {sid}「{s.get('what')}」时，文字里要明明白白写出「{head}」。",
                          sid=sid)
                if not g & art_g:
                    v.add("plant.art", SOFT, "art", f"埋下伏笔 {sid}「{s.get('what')}」时，art.focus 或角色动作里也要有它。", sid=sid)
            if key == "payoff" and g and not g & text_g:
                v.add("payoff.text", SOFT, "page", f"伏笔 {sid}「{s.get('what')}」派上用场时，文字里要写出这样东西。", sid=sid)
            if key == "payoff" and sid == ctx.turn_setup_id and not ctx.turn_allowed:
                v.add("turn.early", SOFT, "page", f"伏笔 {sid}「{s.get('what')}」要留到最后关键时刻才用，这里先别用掉。", sid=sid)
            item = _ledger_item(ctx.ledger, sid) if key == "payoff" and sid not in plants else None
            if item is not None and item.status == "planned":
                v.add("payoff.unplanted", SOFT, "delta", f"伏笔 {sid}「{s.get('what')}」前面还没有埋下就派上了用场。", sid=sid)
    turn = _ledger_item(ctx.ledger, ctx.turn_setup_id) if ctx.is_final_chapter and ctx.is_first_page else None
    if turn is not None and turn.status == "planned":
        v.add("turn.unplanted", SOFT, "page", f"最后关键时刻要用的伏笔 {turn.id}「{turn.what}」前面没有埋下。", sid=turn.id)
    page = _text(lines)
    adds = " ".join(str(x) for x in as_list(d.get("items_add")))
    for item in ctx.removed_items:
        core = re.sub(r"[（(].*?[）)]", "", str(item)).strip()
        if tu.cjk_len(core) >= 2 and core in page and core not in adds:
            v.add("state.removed", SOFT, "page", f"「{core}」前面已经没有了；要让它再出现，得先写清楚它是怎么回来的。", item=core)
    return v


def _echo(lines, ctx) -> list[Violation]:
    """The book's last page brings back page 1's picture with the change (M3 r2 #13), never its words: two whole
    narration or speech lines of page 1 copied replay the trouble (r1 001 n.A.C.A.p4: 「冬眠的日子到了，熊二在干草铺上翻过来，
    覆过去。」「俺睡不着咧！」 in a book about getting to sleep). One line brought back is an echo (r1 003 n.B.C.C.p4); sound
    lines do not count."""
    v = _Acc()
    first = {tu.cjk_only(t) for t in ctx.first_page if isinstance(t, str) and tu.cjk_len(t) >= 2}
    same = [str(l["text"]) for l in lines if isinstance(l, dict) and l.get("k") in ("narr", "say")
            and isinstance(l.get("text"), str) and tu.cjk_only(l["text"]) in first]
    if len(same) >= 2:
        v.add("echo.copy", SOFT, "page", "最后一页照抄了第一页的" + "".join(f"「{t}」" for t in same) + "：回到第一页的画面，但要写出变化"
                                         "——这回主角已经得到了想要的，不要把第一页的句子再抄一遍。", lines=same)
    return v


def _actor_acts(act: str, line: str, people, fc: str) -> bool:
    """The option's actor (the first character named in its text) opens the line and does the option's action there:
    「让熊二坐坏收音机」 / 「熊二一屁股坐扁了旋钮。」 share no bigram but the verb 坐. The action is the character right after
    the actor's name; a function character or an auxiliary (来, 去, 把…) is not one, and then nothing is accepted."""
    found = [(act.find(n), -len(n), k) for k, group in enumerate(people) for n in group if n in act]
    if not found:
        return False
    at, neg, k = min(found)
    verb = act[at - neg:at - neg + 1]
    if not tu.CJK.match(verb or "") or verb in fc or verb in AUX:
        return False
    opener = next((n for n in people[k] if line.startswith(n)), None)
    return opener is not None and verb in line[len(opener):]


def _ack(obj, lines, ctx) -> list[Violation]:
    """The chosen option, as the child saw it (its text) and as the writer was told (hint, token), shows in the first
    two narr/say lines and in the picture (art.focus or an act): a shared bigram (names count only where they stand,
    function characters are read through), or the option's actor opening a line with the option's action."""
    v = _Acc()
    opt, fc = ctx.chosen, ctx.content.function_chars()
    people, names = _people(ctx.content, ctx.bible), _names(ctx.content, ctx.bible)
    act = DECISION.sub("", opt.text)            # 「熊二决定：…」: the frame's 决定 would acknowledge any 决定 line
    target = tu.joined_bigrams(f"{act} {opt.hint} {opt.token}", names, function_chars=fc)
    heads = [str(l.get("text", "")).strip() for l in lines if isinstance(l, dict) and l.get("k") in ("narr", "say")][:2]
    if target and heads and not any(target & tu.joined_bigrams(t, names, function_chars=fc) or
                                    _actor_acts(act, t, people, fc) for t in heads):
        v.add("ack", SOFT, "line:first",
              f"开头一两句就要让读者看到「{opt.text}」带来的后果（{opt.hint}），用自己的话写，不要照抄。")
    if target and not target & tu.joined_bigrams(_art_text(obj), names, function_chars=fc):
        v.add("ack.art", SOFT, "art", f"这一页的画面焦点要画出「{opt.text}」带来的结果。")
    spans = tu.copied_spans(_text(lines), [opt.text])
    if spans:
        v.add("ack.copy", SOFT, "page", "不要照抄选项原话「" + "、".join(spans) + "」。")
    if opt.kind == "idea":                      # a child's idea comes true first (M3 r2 #14: r1 005 「…扑了个空。」)
        idea_g = tu.joined_bigrams(act, names, function_chars=fc)
        done = _idea_done(act, names, fc)
        heads = [(i, str(l.get("text", ""))) for i, l in enumerate(lines)
                 if isinstance(l, dict) and l.get("k") in ("narr", "say")][:2]
        before = ""
        for i, t in heads:
            m = next((x for x in IDEA_FAILS.finditer(t) if not (done and done.search(before + t[:x.start()]))), None)
            if m and (idea_g & tu.joined_bigrams(t, names, function_chars=fc) or _actor_acts(act, t, people, fc)):
                v.add("ack.idea", SOFT, f"line:{i}", f"这是孩子自己想的点子「{act}」：第一页就让它真的做成，不要写「{m.group(0)}」；"
                                                    "麻烦只能在做成以后出现。", hit=m.group(0))
                break
            before += t + "。"
    return v


def _idea_done(act: str, names, fc: str) -> re.Pattern | None:
    """The idea came true: a character of its action (names and function characters out) with a success complement
    (住 到 成 好 紧) — 「一把抱住飞天大沙发」. A failure word after it is the success's result, not a failure (「沙发再也不能
    乱飘了」, 「一点也飞不走了」: review of M3 r2 #14); 「没抱成」 holds its complement inside the failure."""
    s = act or ""
    for w in sorted({n for n in names if n}, key=len, reverse=True):
        s = s.replace(w, "|")
    chars = sorted({ch for ch in s if tu.CJK.match(ch) and ch not in fc})
    return re.compile("[" + "".join(chars) + "][住到成好紧]") if chars else None


def _safety(text, content, where) -> list[Violation]:
    v = _Acc()
    h, s = _hits(content.safety_hard(), text), _hits(content.safety_soft(), text)
    if h:
        v.add("safety", HARD, where, "出现了不适合小朋友的内容「" + "、".join(h) + "」，请换掉。", hits=h)
    if s:
        v.add("safety.soft", SOFT, where, "出现了小朋友可能模仿的危险行为或不该说的话「" + "、".join(s) + "」，请换成安全、温和的说法。",
              hits=s)
    swaps = _swaps(text, content, "safety")
    if swaps:                       # 「死」 for degree with a fixed replacement: made in code (safety.word)
        subs = _subs(content, "safety")
        v.add("safety.word", SOFT, where, "不要用“死”字说程度：" + "、".join(_swap_said(w, subs) for w in swaps) + "。",
              hits=swaps)
    return v


def _swap_said(word: str, subs: dict) -> str:
    """One fixed replacement as a repair message says it: 「捂死」换成「捂紧」, or 去掉「死死」 for a word that goes."""
    return f"「{word}」换成「{subs[word]}」" if subs[word] else f"去掉「{word}」"


def _art_safety(obj, content: Content) -> list[Violation]:
    """The picture brief is drawn, not read aloud, but B1's image prompt copies its texts word for word (_art_parts:
    focus, place, time, weather, shot, mood, each act and face): r1 004 n.C.p1's text was fixed while its act kept
    「死死捂住嘴巴和鼻子，脸憋得通红」 (M3 r2 review, R2CHK-1). Its parts (kept apart, so no pattern joins two of them) get
    the soft patterns and the hard ones except the spoken insults (safety.spoken: 001 n.p3's bird 「停在屋顶闭嘴」 is a beak,
    a face 「紧闭嘴巴」 a closed mouth) — one safety.art, hard when a hard pattern hits — and its fixed replacements are made
    in code like a line's (safety.word, adult.word on "art")."""
    v = _Acc()
    text = "。".join(_art_parts(obj))
    if not text:
        return v
    spoken = set(content.phrases.get("safety", {}).get("spoken", []))
    h = _hits([p for p in content.safety_hard() if p.pattern not in spoken], text)
    s = _hits(content.safety_soft(), text)
    if h or s:
        v.add("safety.art", HARD if h else SOFT, "art",
              "画面说明（art 的各项和角色的动作、表情）里有" + ("不适合小朋友的内容" if h else "小朋友可能模仿的危险动作")
              + "「" + "、".join(h + s) + "」：插画会照着画出来，请换成安全、温和的动作。", hits=h + s)
    for code, key in (("safety.word", "safety"), ("adult.word", "adult")):
        swaps = _swaps(text, content, key)
        if swaps:
            subs = _subs(content, key)
            v.add(code, SOFT, "art", "画面说明里" + "、".join(_swap_said(w, subs) for w in swaps) + "。", hits=swaps)
    return v


# ---------------------------------------------------------------- forks
# Verbs that use a thing (the turn object): 举着权杖, 吹响…口哨, 把蜂蜜饼掰… (把/将 put the thing before its verb); verbs of
# seeing, looking for or keeping do not (盯着口哨, 去找丢了的口哨): the turn object may be seen before the finale.
USE_VERBS = frozenset("用拿举握抓抱拎提捧掏吹敲挥摇甩扔抛按塞套罩盖照撬戳捅插砸踩坐骑吃喝舔咬戴穿拉推拽扯拔摘点烧倒泼抹涂粘贴系绑挂"
                      "放递交送给换借开扣拍弹拧搬扛背顶撑架堵卡掰把将")
SEE_VERBS = frozenset("看瞧盯望瞅找寻想听闻数问等指认记藏留收保护")
USE_AFTER = re.compile("一[" + "".join(sorted(USE_VERBS)) + "]")    # 口哨一吹, 权杖一挥


def _uses(s: str, hg: set) -> bool:
    """In one option string, a clause names the thing (one of its bigrams `hg`) and the nearest verb before it is a
    using one (USE_VERBS, not SEE_VERBS), or a using verb follows it after 一 (口哨一吹)."""
    for clause in re.split(r"[，,。！？!?；;…]", s):
        at = min((i for i in range(len(clause) - 1) if clause[i:i + 2] in hg), default=None)
        if at is None:
            continue
        verb = next((ch for ch in reversed(clause[:at]) if ch in USE_VERBS or ch in SEE_VERBS), "")
        if verb in USE_VERBS or USE_AFTER.search(clause[at + 2:at + 5]):
            return True
    return False


def action_token(token: str) -> bool:
    """The token is an action (捂耳朵, 再抢口哨), not a thing: it opens with an action verb (TOKEN_VERB), the word from
    that verb on is not a noun of TOKEN_NOUNS (盖子, 飞天大沙发), and no 的 makes the verb a modifier of a thing (飞走的工具,
    皮鞋里的松果)."""
    t = tu.cjk_only(token)
    m = TOKEN_VERB.match(t)
    return m is not None and not t[m.start(1):].startswith(TOKEN_NOUNS) and "的" not in t[:-1]


def _fetched(text: str, ctx: ForkCtx) -> str:
    """The name of someone on the last page (ForkCtx.present, any of their names) whom the option goes to fetch: 找 X
    (「找熊大帮忙赶蜜蜂」, 「去大树洞找熊大…」), or 喊/叫/请 X 来/过来/回来/帮忙 (「去洞外喊熊二来帮忙」). An option that says what X
    does is the fix itself (「请赵琳用背包带绊树洞」, 「叫熊二捂住耳朵」): the reviewer's 「(找|喊|请|叫)…X」 would send it back; X
    followed by 的 owns what is looked for (「找熊大的帽子」)."""
    c = ctx.content
    for shown in ctx.present:
        if not isinstance(shown, str) or not shown:
            continue
        ids = [cid for cid in list(c.characters) + list(c.minor) if shown in c.names(cid)]
        for n in sorted({shown} | {x for cid in ids for x in c.names(cid)}, key=len, reverse=True):
            e = re.escape(n)
            if re.search(rf"找[^，。！？]{{0,4}}{e}(?!的)|(喊|叫|请)[^，。！？]{{0,4}}{e}(来|过来|回来|帮忙)", text):
                return shown
    return ""


ASKING = re.compile(r"怎么|咋|如何|谁|什么|啥|哪|为什么|多少")      # the clause of a fork question that asks
COMPLEMENTS = frozenset("走过来去上下起住到掉开完好成")             # 抢过 → 抢走 is the same act


def _unseen(q: str, ctx: ForkCtx) -> list[str]:
    """The words of the fork question's situation that the world line never wrote (q.unseen, log-only; findings #12 fix
    3): in its clauses that neither ask (怎么, 谁…) nor only say 「find a way」, runs of two or more content characters
    (names and places out) that no content bigram of the line covers and that hold a character the line never used —
    direction and result complements aside. r1 003 n.B.C 「树洞叼走口哨，怎么夺回来？」 → 叼走. Nothing without the line."""
    line = str(ctx.page_text or "")
    if not line.strip() or not q:
        return []
    c, fc = ctx.content, ctx.content.function_chars()
    names = _names(c, ctx.bible)
    known = tu.content_bigrams(line, remove=names, function_chars=fc) | tu.STOP_BIGRAMS
    used = set(tu.cjk_only(line))
    s = q
    for w in sorted({n for n in names if n}, key=len, reverse=True):
        s = s.replace(w, "|")
    out: list[str] = []
    for clause in re.split(r"[，,；;、？?！!。]", s):
        if not clause.strip() or HOWTO.search(clause) or ASKING.search(clause):
            continue
        for run in re.findall(r"[一-鿿]+", clause):
            for part in re.split(f"[{re.escape(fc)}]+", run) if fc else [run]:
                covered = [False] * len(part)
                for i in range(len(part) - 1):
                    if part[i:i + 2] in known:
                        covered[i] = covered[i + 1] = True
                cur = ""
                for ch, cov in zip(part + "|", covered + [True]):
                    if not cov:
                        cur += ch
                        continue
                    if len(cur) >= 2 and any(x not in used and x not in COMPLEMENTS for x in cur):
                        out.append(cur)
                    cur = ""
    return out


def validate_choice(obj: dict, ctx: ForkCtx) -> list[Violation]:
    v = _Acc()
    if not isinstance(obj, dict) or "__parse_error__" in obj:
        v.add("parse", HARD, "choice", "岔路口这一行不是合法的 JSON，请按格式重写。")
        return v
    if obj.get("type") != "choice":
        v.add("schema.type", HARD, "choice", "这一行的 type 必须是 choice。")
        return v
    c, fc = ctx.content, ctx.content.function_chars()
    q = first_str(obj.get("q")).strip()
    if not q:
        v.add("fork.q", SOFT, "q", "请写出岔路口的问题 q。")
    elif tu.cjk_len(q) > 15:
        v.add("fork.q_len", SOFT, "q", "问题太长了，十五个字以内。")
    if GENERIC_Q.match(q):
        v.add("fork.generic", SOFT, "q", "问题要说清眼下的处境，不要只问“怎么办”。")
    if tu.cjk_len(q) >= 2 and not _as_question(q).endswith(("？", "?")):     # too long for 「，怎么办？」 even in code
        v.add("fork.q_ask", SOFT, "q", "问题要写成一句十五字以内的问句：说清是谁、什么东西出了什么事，比如「海螺要被踩碎了，怎么办？」。")
    if tu.has_latin(q) or tu.has_digit(q) or tu.has_emoji(q):          # shown on the fork banner and read aloud
        v.add("fork.script", SOFT, "q", "问题只能用汉字。")
    raw = obj.get("opts")
    opts = [o for o in raw if isinstance(o, dict)] if isinstance(raw, list) else []
    if len(opts) < 2:
        v.add("fork.opts", HARD, "opts", "岔路口要有三个选项。")
        return v
    if len(opts) != 3:
        v.add("fork.count", SOFT, "opts", f"应该正好三个选项，现在有{len(opts)}个。")
    opts = opts[:3]
    kinds, passive = [], 0
    for i, o in enumerate(opts):
        where = f"opts:{i}"
        text = first_str(o.get("text")).strip()
        hint, tok = first_str(o.get("hint")).strip(), first_str(o.get("token"))      # the ending recap quotes the token
        if not text:
            v.add("fork.opt_empty", HARD, where, f"第{i + 1}个选项是空的。")
            continue
        if tu.cjk_len(text) > 12:
            v.add("fork.opt_len", SOFT, where, f"第{i + 1}个选项「{text}」太长了，十二个字以内。")
        kinds.append(o.get("kind"))
        if o.get("kind") not in OPTION_KINDS:
            v.add("fork.kind", SOFT, where, f"第{i + 1}个选项的 kind 要是 careful、bold 或 silly。")
        if not hint:
            v.add("fork.hint", SOFT, where, f"第{i + 1}个选项缺少 hint（会带来的具体后果）。")
        if not 2 <= tu.cjk_len(tok) <= 6:
            v.add("fork.token", SOFT, where, f"第{i + 1}个选项的 token 要是二到六个字：这个选择留下的一样东西、一个地方或一个伙伴（名词）。")
        elif action_token(tok):                         # log-only (R2CHK-11): 26 of 36 r1 forks, each a repair call
            v.add("fork.token_action", SOFT, where, f"第{i + 1}个选项的 token「{o.get('token')}」是一个动作；token 要写这个选择"
                                                    "留下的一样东西、一个地方或一个伙伴（名词），比如「蜂蜜罐」「大树洞」。")
        here = _fetched(text, ctx)
        if here:                                       # r1 002 n.B 「去洞外喊熊二来帮忙」 after 熊二 spoke on that page
            v.add("fork.present", SOFT, where, f"第{i + 1}个选项：{here}就在这儿，不用去找；写成让{here}做什么。", who=here)
        if PASSIVE.match(text):
            passive += 1
        if PERSUADE.search(text):
            v.add("fork.persuade", SOFT, where, f"第{i + 1}个选项不要写成“劝谁别做什么”，请写一个角色亲手做的具体动作。")
        unscripted = [tu.has_latin(s) or tu.has_digit(s) or tu.has_emoji(s) for s in (text, tok)]
        if any(unscripted):                            # text: the card shows it and B1 reads it aloud (lean: like hard)
            v.add("fork.script", SOFT, where, f"第{i + 1}个选项（和它的 token）只能用汉字。", text=unscripted[0])
        meta = [w for w in META_WORDS if any(w in s for s in (text, hint, tok))]
        if meta:                                       # shown on the card, read aloud, quoted to the next writer
            v.add("meta", SOFT, where, f"第{i + 1}个选项里不要出现故事外的词「{'、'.join(meta)}」。", hits=meta)
        grown = _adult("。".join((text, hint, tok)), c)
        if grown:                                      # r1 004: 「用跑调的歌声气走条款」「…红漆交差」
            v.add("adult", SOFT, where, f"第{i + 1}个选项（和它的后果）里不要用大人才用的词「{'、'.join(grown)}」，"
                                        "换成孩子听得懂的说法。", hits=grown)
    named = [k for k in kinds if k in OPTION_KINDS]
    if len(set(named)) < len(named):
        v.add("fork.kinds", SOFT, "opts", "三个选项的 kind 要各不相同：careful、bold、silly 各一个。")
    if passive and ctx.state.count("passive_opts") + passive > 1:
        v.add("fork.passive", SOFT, "opts", "“问问、看看、想想”这类选项一本书最多一个，请换成角色亲手做的事。")
    turn = ctx.bible.turn_setup()
    if turn and not ctx.is_final_fork:
        head = head_noun(turn.get("what", ""))
        hg = tu.content_bigrams(head, remove=_names(c, ctx.bible), function_chars=fc)
        for i, o in enumerate(opts):
            if hg and any(_uses(first_str(o.get(k)), hg) for k in ("text", "hint")):
                v.add("fork.turn_early", SOFT, f"opts:{i}", f"第{i + 1}个选项用上了「{head}」：它要留到最后关键时刻才用，"
                                                            "选项里可以看见它、提到它，但不要拿它来解决问题。")
    ideas = obj.get("ideas", [])
    if not isinstance(ideas, list) or any(not isinstance(x, str) or tu.cjk_len(x) > 10 for x in ideas):
        v.add("fork.ideas", SOFT, "ideas", "ideas 是两个孩子可能想到的点子，每个十个字以内。")
    # every string of the fork, kept apart (水 + 枪 glued hid a hit): tokens are shown in the recap, hints are quoted
    # to later writers
    v += _safety("。".join([q] + [first_str(o.get(k)) for o in opts for k in ("text", "hint", "token")]), c, "choice")
    meta = [w for w in META_WORDS if w in q]
    if meta:
        v.add("meta", SOFT, "q", "问题里不要出现故事外的词「" + "、".join(meta) + "」。")
    grown = _adult(q, c)
    if grown:                                          # r1 004: 「怎么解决克扣工资的怪规矩？」
        v.add("adult", SOFT, "q", f"问题里不要用大人才用的词「{'、'.join(grown)}」，换成孩子听得懂的说法。", hits=grown)
    unseen = _unseen(q, ctx)
    if unseen:                                         # log-only: r1 003 n.B.C 「树洞叼走口哨…」, 叼走 on no page
        v.add("q.unseen", SOFT, "q", f"问题里的「{'、'.join(unseen)}」前面的页里没有写出来：q 只说最后一页上已经写出来的事。",
              words=unseen)
    # what the child sees and hears (banner, cards, chips) and the next writer is quoted: a character off the line whom
    # the line's pages never named (a page repair took him out) is sent back; a page that kept him keeps the fork's word
    shown = "。".join([q] + [first_str(o.get(k)) for o in opts for k in ("text", "hint", "token")]
                     + [x for x in _list(ideas) if isinstance(x, str)])
    away = [cid for cid in _off_line(ctx, shown) if not mentions(c, ctx.bible, cid, str(ctx.page_text or ""))]
    if away:
        v.add("cast.outside", SOFT, "choice", f"{'、'.join(c.name(x) for x in away)} 不在这本书的角色里，前面的页面里也没有出现；"
                                              f"岔路口的问题、选项和点子只写本书的角色{_our_cast(ctx)}。", who=away)
    return v


# ---------------------------------------------------------------- end / plan / bible heads
def check_strings(texts, content: Content) -> list[str]:
    """Problem codes in short display strings (titles, world fields, ending names, idea chips): safety (hard and
    soft, the 「死」 words with a fixed replacement too), adult words, Latin letters, Arabic digits, emoji,
    story-external words and Tier A phrases. Non-strings are skipped."""
    texts = [texts] if isinstance(texts, str) else (list(texts) if isinstance(texts, (list, tuple)) else [])
    found: set[str] = set()
    for t in texts:
        if not isinstance(t, str) or not t.strip():
            continue
        if _hits(content.safety_hard(), t):
            found.add("safety")
        if _hits(content.safety_soft(), t) or _swaps(t, content, "safety"):
            found.add("safety.soft")
        if _adult(t, content) or _swaps(t, content, "adult"):
            found.add("adult")
        if tu.has_latin(t):
            found.add("script.latin")
        if tu.has_digit(t):
            found.add("script.digit")
        if tu.has_emoji(t):
            found.add("script.emoji")
        if any(w in t for w in META_WORDS):
            found.add("meta")
        if _hits(content.tier_a(), t):
            found.add("tierA")
    return sorted(found)


def _problems(found: list[str]) -> str:
    return "、".join(PROBLEMS.get(x, x) for x in found)


def validate_end(obj, content: Content | None = None) -> list[Violation]:
    v = _Acc()
    if not isinstance(obj, dict) or "__parse_error__" in obj or obj.get("type") != "end":
        v.add("parse", HARD, "end", "结尾这一行要是 {\"type\":\"end\",\"title\":\"结局名\"}。")
        return v
    title = obj.get("title").strip() if isinstance(obj.get("title"), str) else ""
    if not title:
        v.add("end.title", HARD, "end", "请写出结局名 title。")
    elif tu.cjk_len(title) > 10 or tu.has_latin(title):
        v.add("end.title_len", SOFT, "end", "结局名十个字以内，只用汉字。")
    bad = check_strings([title], content) if content is not None else []
    if bad:
        v.add("end.text", SOFT, "end", f"结局名里不要出现{_problems(bad)}。", problems=bad)
    return v


def validate_plan(obj) -> list[Violation]:
    v = _Acc()
    text = obj.get("text") if isinstance(obj, dict) else None
    if not isinstance(obj, dict) or obj.get("type") != "plan" or not isinstance(text, str) or not text.strip():
        v.add("plan.missing", SOFT, "plan", "缺少 plan 行。")
    elif tu.cjk_len(text) > 60:
        v.add("plan.len", SOFT, "plan", "plan 太长了，六十字以内。")
    return v


def validate_title(obj, content: Content | None = None) -> list[Violation]:
    v = _Acc()
    title = obj.get("title") if isinstance(obj, dict) else None
    if not isinstance(obj, dict) or obj.get("type") != "title" or not isinstance(title, str) or not title.strip():
        v.add("title.missing", HARD, "title", "第一行要是 {\"type\":\"title\",\"title\":\"书名\",\"logline\":\"一句话\"}。")
        return v
    if tu.cjk_len(title) > 12:
        v.add("title.len", SOFT, "title", "书名十二个字以内。")
    if tu.cjk_len(str(obj.get("logline", ""))) > 40:
        v.add("title.logline", SOFT, "title", "一句话简介四十个字以内。")
    bad = check_strings([title, obj.get("logline")], content) if content is not None else []
    if bad:
        v.add("head.text", SOFT, "title", f"书名和简介里不要出现{_problems(bad)}。", problems=bad)
    return v


def _world_text(obj: dict) -> list:
    """The display text of a world line; ids (hero, cast, era, antagonist.who) are not text."""
    out = [obj.get("want"), obj.get("oddity"), obj.get("refrain")] + _list(obj.get("places"))
    for key, names in (("rule", ("text", "trigger", "effect", "limit")), ("guest", ("name", "look", "want", "manner")),
                       ("antagonist", ("motive",))):
        d = obj.get(key) if isinstance(obj.get(key), dict) else {}
        out += [d.get(n) for n in names]
    return out


def _cast_id(content: Content, x) -> str | None:
    """A cast entry as a canon id: the id itself, a character's name or alias (熊大), or an id with a suffix the model
    made up for a copy (xiongda_boss, xiongda2); None for anything else (guest, minor characters, unknown ids)."""
    if not isinstance(x, str) or not x.strip():
        return None
    x = x.strip()
    ids = content.cast_ids()
    if x in ids:
        return x
    named = next((cid for cid in ids if x in content.names(cid)), None)
    if named:
        return named
    m = re.match(r"([a-z]+)[\W_\d]", x)
    return m.group(1) if m and m.group(1) in ids else None


def _fix_cast(o: dict, content: Content) -> None:
    """hero and cast in place (M3 r2 #6, findings #14: card c23 「三个熊大」 lost its opening twice to world.cast): both as
    canon ids (_cast_id), the cast without unknown entries and duplicates, the hero first, at most four. A hero that is
    no canon character stays as it is (world.hero asks for a repair); a cast below two stays hard (world.cast)."""
    raw = o.get("cast")
    if isinstance(raw, str):
        raw = JOINED.split(raw)
    if not isinstance(raw, list):
        return
    hero = _cast_id(content, o.get("hero"))
    if hero:
        o["hero"] = hero
    cast = list(dict.fromkeys(x for x in (_cast_id(content, y) for y in raw) if x))
    if hero:
        cast = [hero] + [x for x in cast if x != hero]
    o["cast"] = cast[:4]


def _swap_world(o: dict, content: Content) -> None:
    """The fixed replacements of the safety and adult lists in the world line's descriptive text, in place: the rule's
    text goes onto page 2 (r1 003 「…树洞就必定迈开腿走三步」, 002 「…在场的人就得原地转圈」). Names and places stay as they are."""
    for k in ("want", "oddity", "refrain"):
        if isinstance(o.get(k), str):
            o[k] = swap_words(o[k], content)
    for key, names in (("rule", ("text", "trigger", "effect", "limit")), ("guest", ("look", "want", "manner")),
                       ("antagonist", ("motive",))):
        d = o.get(key)
        for n in names if isinstance(d, dict) else ():
            if isinstance(d.get(n), str):
                d[n] = swap_words(d[n], content)


def fix_world(obj, content: Content | None = None):
    """The world line's shapes fixed without a call (pure, like fix_setups). With content, the cast and hero are cleaned
    (_fix_cast) and the descriptive text gets the fixed replacements of the safety and adult lists (_swap_world).
    antagonist.who becomes one id: a list (the poachers 大马猴 and 二狗 together) or a joined string keeps its
    first cast member, a cast member's name becomes its id (with content), any other non-string becomes "". A repair may
    well send the same list back, and the bible needs one id. A string that names no cast member is kept: the check
    asks for one repair."""
    if not isinstance(obj, dict):
        return obj
    o = copy.deepcopy(obj)
    if content is not None:
        _fix_cast(o, content)
        _swap_world(o, content)
    if not isinstance(o.get("antagonist"), dict):
        return o
    cast = [x for x in _list(o.get("cast")) if isinstance(x, str)]
    ids = {x: x for x in cast} | ({content.name(x): x for x in cast} if content is not None else {})
    who = o["antagonist"].get("who")
    if isinstance(who, str) and who not in cast:
        who = next((ids[w] for w in JOINED.split(who) if w in ids), who)
    elif isinstance(who, list):
        who = next((ids[w] for w in who if isinstance(w, str) and w in ids), "")
    o["antagonist"]["who"] = who if isinstance(who, str) else ""
    return o


def validate_world(obj, content: Content) -> list[Violation]:
    v = _Acc()
    if not isinstance(obj, dict) or obj.get("type") != "world":
        v.add("world.parse", HARD, "world", "这一行要是 type 为 world 的设定。")
        return v
    cast = obj.get("cast")
    if (not isinstance(cast, list) or not all(isinstance(x, str) for x in cast) or not 2 <= len(cast) <= 4
            or not set(cast) <= content.cast_ids()):
        v.add("world.cast", HARD, "world", "cast 要是两到四个角色表里的角色 id。")
        cast = [x for x in cast if isinstance(x, str)] if isinstance(cast, list) else []
    if obj.get("hero") not in cast:
        v.add("world.hero", HARD, "world", "hero 要是 cast 里的第一个角色。")
    if not str(obj.get("want", "")).strip():
        v.add("world.want", HARD, "world", "要写出主角想要的具体东西 want。")
    rule = obj.get("rule") if isinstance(obj.get("rule"), dict) else {}
    if not all(str(rule.get(k, "")).strip() for k in ("text", "trigger", "effect")):
        v.add("world.rule", HARD, "world", "rule 要有 text、trigger、effect。")
    elif VIRTUE.search(str(rule.get("trigger", ""))):
        v.add("rule.virtue", SOFT, "world", "怪规矩不要用“夸人、说真话、分享、帮助”这类美德来触发，换一个好玩又数得清的触发条件。")
    if any(RULE_META.search(str(rule.get(k, ""))) for k in ("text", "trigger", "effect", "limit")):
        v.add("rule.meta", SOFT, "world", "怪规矩只有一条，从头到尾不变：一个看得见、能数清的触发对应一个看得见的结果；不要写“每一站"
                                          "都有一条规矩”“按规矩做”这种会变的规矩。")      # no r1 trigger as an example (R2CHK-6)
    names = [n for cid in _list(obj.get("cast")) if isinstance(cid, str) for n in content.names(cid)]
    names += [x for x in [(obj.get("guest") or {}).get("name") if isinstance(obj.get("guest"), dict) else None]
              + _list(obj.get("places")) if isinstance(x, str) and x]
    fc = content.function_chars()
    said = tu.content_bigrams(str(obj.get("refrain", "")), remove=names, function_chars=fc)
    if len(said & tu.content_bigrams(str(rule.get("text", "")), remove=names, function_chars=fc)) >= 2:
        v.add("refrain.trigger", SOFT, "world", "复沓句不要就是触发怪规矩的那句话（喊了它，规矩就得起作用）；"
                                                "换一句跟着故事走、孩子能跟着喊的短句。")
    raw_guest = obj.get("guest")
    guest = raw_guest if isinstance(raw_guest, dict) else {}
    if (raw_guest and not isinstance(raw_guest, dict)) or (guest.get("name") and not isinstance(guest["name"], str)):
        v.add("world.guest", HARD, "world", "guest 要是一个对象，guest.name 是一个名字（字符串）；客串角色最多一个。")
    if MANNER_BAD.search(str(guest.get("manner", ""))):
        v.add("guest.manner", SOFT, "world", "客串角色的 manner 只描述说话的样子，不要规定口头禅，也不要写“必、每次、一定、总”。")
    places = obj.get("places")
    if not isinstance(places, list) or not 1 <= len(places) <= 3:
        v.add("world.places", SOFT, "world", "places 写一到三个地点。")
    refrain = str(obj.get("refrain", "")).strip()
    if not refrain or tu.cjk_len(refrain) > 8:
        v.add("world.refrain", SOFT, "world", "复沓句 refrain 八个字以内。")
    ant = obj.get("antagonist") if isinstance(obj.get("antagonist"), dict) else {}
    if ant.get("who") not in ("", None) and ant.get("who") not in cast:
        v.add("world.antagonist", SOFT, "world", "antagonist.who 要是 cast 里的角色，或者留空。")
    if not isinstance(obj.get("era"), str) or obj.get("era") not in content.eras:
        v.add("world.era", SOFT, "world", "era 只能是 logger、adventure 或 any。")
    bad = check_strings(_world_text(obj), content)
    if bad:
        v.add("head.text", SOFT, "world", f"设定里不要出现{_problems(bad)}。", problems=bad)
    return v


def validate_setups(obj, content: Content | None = None) -> list[Violation]:
    """With content, the words of each what and where get the display checks: a safety hit or an adult word left after
    fix_setups's replacements is setups.text (soft; the writer asks for one repair) — every brief quotes the setups (M3 r2
    review, R2CHK-16: r1 003's 「挂在树洞内壁上的旧口哨」 in 9 of its 10 briefs)."""
    v = _Acc()
    items = obj.get("items") if isinstance(obj, dict) and isinstance(obj.get("items"), list) else []
    items = [i for i in items if isinstance(i, dict)]
    if not items:
        v.add("setups.missing", HARD, "setups", "setups 要有两到三个伏笔。")
        return v
    ids = [i.get("id") for i in items]
    if not all(isinstance(x, str) and x.strip() for x in ids) or len(set(ids)) != len(ids):     # strings before set()
        v.add("setups.ids", HARD, "setups", "伏笔编号要是各不相同的字符串（\"S1\"、\"S2\"……）。")
    if any(not (isinstance(i.get("what"), str) and i["what"].strip()) for i in items):
        v.add("setups.what", HARD, "setups", "每个伏笔都要写清楚是什么东西。")
    if not 2 <= len(items) <= 3:            # one turn, at most one gag and one clue (M3 r2 #5: fewer must-dos)
        v.add("setups.count", SOFT, "setups", "伏笔要两到三个：恰好一个 turn，gag 和 clue 最多各一个。")
    if any(i.get("role") not in ("turn", "gag", "clue") for i in items):
        v.add("setups.role", SOFT, "setups", "伏笔的 role 只能是 turn、gag 或 clue。")
    if sum(1 for i in items if i.get("role") == "turn") != 1:
        v.add("setups.turn", SOFT, "setups", "恰好一个伏笔的 role 是 turn（留到最后关键时刻才用）。")
    if content is not None:
        bad = [s for i in items for s in (i.get("what"), i.get("where")) if isinstance(s, str)
               and {"safety", "safety.soft", "adult"} & set(check_strings([s], content))]
        if bad:
            v.add("setups.text", SOFT, "setups", "伏笔里不要出现大人才用的词或危险的事：" + "、".join(f"「{s}」" for s in bad)
                  + "，换成讲给五岁孩子听的说法。", texts=bad)
    return v


def fix_setups(obj: dict, content: Content | None = None) -> dict:
    """Roles fixed in code (one turn: the first, else the first item; any other role becomes gag), then at most one gag
    and one clue besides the turn, in the model's order (M3 r2 #5): a fourth setup was one more must-do in every brief.
    Nothing is planted yet when the setups line arrives, and a twist that cites a dropped setup is not usable. With
    content, each what and where gets the fixed replacements of the safety and adult lists (内壁上 → 墙上: R2CHK-16), and a
    `where` that is no string goes."""
    o = copy.deepcopy(obj)
    items = [i for i in _list(o.get("items")) if isinstance(i, dict)]
    for i in items:
        if "where" in i and not isinstance(i["where"], str):
            del i["where"]
        for k in ("what", "where") if content is not None else ():
            if isinstance(i.get(k), str):
                i[k] = swap_words(i[k], content)
    seen_turn = False
    for i in items:
        if i.get("role") == "turn" and not seen_turn:
            seen_turn = True
        elif i.get("role") == "turn" or i.get("role") not in ("turn", "gag", "clue"):
            i["role"] = "gag"
    if not seen_turn and items:
        items[0]["role"] = "turn"
    roles: set = set()
    o["items"] = [i for i in items if not (i["role"] in roles or roles.add(i["role"]))]
    return o


def validate_secret(obj, setup_ids, content: Content) -> list[Violation]:
    v = _Acc()
    if not isinstance(obj, dict) or obj.get("type") != "secret":
        v.add("secret.parse", SOFT, "secret", "缺少 secret 行。")
        return v
    payoffs = obj.get("payoffs") if isinstance(obj.get("payoffs"), dict) else {}
    if not set(payoffs) <= set(setup_ids):
        v.add("secret.payoffs", SOFT, "secret", "payoffs 只能写本书伏笔编号。")
    twists = obj.get("twists") if isinstance(obj.get("twists"), list) else []
    if any(not isinstance(t, dict) or not all(t.get(k) not in (None, "") for k in ("idea", "setup", "clue"))
           or not isinstance(t.get("typicality"), (int, float)) for t in twists):
        v.add("secret.twists", SOFT, "secret", "每个意外真相都要有 idea、setup、clue 和 typicality（零到一之间的数）。")
    endings = obj.get("endings") if isinstance(obj.get("endings"), dict) else {}
    text = "".join(str(x) for x in endings.values())
    if not {"warm", "twist", "funny"} <= set(endings) or _hits(content.tier_a(), text):
        v.add("secret.endings", SOFT, "secret", "endings 要有 warm、twist、funny 三种结局的样子，而且不要说道理。")
    strings = [x for t in twists if isinstance(t, dict) for x in (t.get("idea"), t.get("clue"))] + list(endings.values())
    strings += list(payoffs.values()) + [obj.get("low")]
    bad = sorted({c for x in strings if isinstance(x, str) for c in check_strings([x], content)}
                 & {"safety", "safety.soft", "adult"})
    if bad:                                           # logged; fix_secret drops what carries them
        v.add("secret.text", SOFT, "secret", f"秘密设定里不要出现{_problems(bad)}。", problems=bad)
    return v


def _unfit(s, content: Content) -> bool:
    """A secret string the writer must not be told: a safety hit (hard or soft) or an adult word (check_strings)."""
    return bool({"safety", "safety.soft", "adult"} & set(check_strings([s], content)))


def fix_secret(obj, content: Content) -> tuple:
    """(secret line, fixes) — pure. The secret reaches the writer through the briefs (the truth of a twist and its
    clue, the ending templates, what the low point loses), so the safety and adult lists apply to it as to a page
    (M3 r2 findings #4, #15): fixed replacements are made (secret.word), and a twist, an ending template, a payoff or the
    low that still has a safety hit or an adult word is dropped (secret.twist, secret.ending:<family>, secret.payoff,
    secret.low) — there is no repair for the secret line, and the director works without the dropped part (r1 004's
    twist 「天上的怪规矩是李老板定的克扣工资条款」 became a whole plot about wage clauses)."""
    if not isinstance(obj, dict):
        return obj, []
    o, fixes = copy.deepcopy(obj), []

    def swap(x):
        if not isinstance(x, str):
            return x
        t = swap_words(x, content)
        if t != x and "secret.word" not in fixes:
            fixes.append("secret.word")
        return t
    if isinstance(o.get("twists"), list):
        kept = []
        for t in o["twists"]:
            t = {k: swap(x) for k, x in t.items()} if isinstance(t, dict) else t
            if isinstance(t, dict) and any(_unfit(t.get(k), content) for k in ("idea", "clue")):
                fixes.append("secret.twist")
                continue
            kept.append(t)
        o["twists"] = kept
    for key, code in (("endings", "secret.ending:"), ("payoffs", "secret.payoff")):
        if isinstance(o.get(key), dict):
            d = {k: swap(x) for k, x in o[key].items()}
            gone = [k for k, x in d.items() if _unfit(x, content)]
            fixes += [code + str(k) if code.endswith(":") else code for k in gone]
            o[key] = {k: x for k, x in d.items() if k not in gone}
    if isinstance(o.get("low"), str):
        o["low"] = swap(o["low"])
        if _unfit(o["low"], content):
            o["low"] = ""
            fixes.append("secret.low")
    return o, fixes


def validate_chapter(pages: list[dict], check: ChapterCheck) -> list[Violation]:
    v = _Acc()
    fc = check.content.function_chars()
    pages = [p for p in pages if isinstance(p, dict)]
    deltas = [p.get("delta") if isinstance(p.get("delta"), dict) else {} for p in pages]
    paid = {s for d in deltas for s in as_list(d.get("payoff")) if isinstance(s, str)}
    planted = {s for d in deltas for s in as_list(d.get("plant")) if isinstance(s, str)}
    text = "".join(_text(_lines(p)) for p in pages)
    for sid in check.due_payoffs:
        if sid not in paid:
            s = resolve_id(check.bible, check.ledger, sid) or {}
            v.add("payoff.missing", SOFT, "chapter", f"这一章要让伏笔 {sid}「{s.get('what', '')}」派上用场。", scope=STRUCT, sid=sid)
    for sid in check.must_plant:
        if sid not in planted:
            s = resolve_id(check.bible, check.ledger, sid) or {}
            v.add("plant.missing", SOFT, "chapter", f"这一章要不起眼地埋下伏笔 {sid}「{s.get('what', '')}」。", scope=STRUCT, sid=sid)
    if check.token:
        tg = tu.content_bigrams(check.token, function_chars=fc)
        delta_text = " ".join(str(x) for d in deltas for k in ("items_add", "items_remove", "flags") for x in as_list(d.get(k)))
        seen = text + " " + delta_text
        names = _names(check.content, check.bible)
        og = tu.joined_bigrams(DECISION.sub("", check.option_text or ""), names, function_chars=fc)
        if (tg and not tg & tu.content_bigrams(seen, function_chars=fc)
                and not og & tu.joined_bigrams(seen, names, function_chars=fc)):
            v.add("token.missing", SOFT, "chapter", f"这一章要写出刚才那个选择带来的「{check.token}」。", scope=STRUCT)
    turn = check.bible.turn_setup()
    if check.is_finale and turn and turn.get("id") not in paid:
        v.add("turn.missing", SOFT, "chapter", f"第一页就要用伏笔 {turn.get('id')}「{turn.get('what')}」来解决难题。", scope=STRUCT)
    if check.needs_rule and not any(d.get("rule_used") is True for d in deltas):
        v.add("rule.unused", SOFT, "chapter", "这一章要让怪规矩真的起一次作用。", scope=STRUCT)
    if check.reveal:                 # the truth in words (M3 r2 #11): r1 005's low point never said it, 004's left it unread
        names = _names(check.content, check.bible)
        rg = tu.content_bigrams(check.reveal, remove=names + list(REVEAL_STOP), function_chars=fc)
        if rg and not rg & tu.content_bigrams(text, remove=names, function_chars=fc):
            v.add("reveal.missing", SOFT, "chapter", f"这一章要用一句旁白或台词说清楚真相：{check.reveal}（用孩子听得懂的话说，"
                                                     "不要照抄）。", scope=STRUCT)
    return v


# ---------------------------------------------------------------- soft fixes and usage
def _line_index(where: str) -> int | None:
    m = re.fullmatch(r"line:(\d+)", where or "")
    return int(m.group(1)) if m else None


def _protected(obj, ctx) -> set[int]:
    lines = _lines(obj)
    keep = {0, len(lines) - 1}
    d = obj.get("delta") if isinstance(obj.get("delta"), dict) else {}
    fc = ctx.content.function_chars()
    for sid in as_list(d.get("plant")) + as_list(d.get("payoff")):
        s = resolve_id(ctx.bible, ctx.ledger, sid)
        g = tu.content_bigrams(s["what"], function_chars=fc) if s else set()
        for i, l in enumerate(lines):
            if g and isinstance(l, dict) and g & tu.content_bigrams(str(l.get("text", "")), function_chars=fc):
                keep.add(i)
    return keep


def soft_fix_page(obj: dict, violations: list[Violation], ctx: PageCtx) -> tuple[dict, list[str]]:
    o = normalize_page(obj)
    lines = _lines(o)
    fixes: list[str] = []
    d = o.get("delta") if isinstance(o, dict) and isinstance(o.get("delta"), dict) else None
    if d is not None and any(x.code == "id.setup" for x in violations):      # unknown ids: dropped, never repaired
        for key in ("plant", "payoff"):
            ids = as_list(d.get(key))
            known = [sid for sid in ids if resolve_id(ctx.bible, ctx.ledger, sid) is not None]
            if key in d:
                d[key] = known
            fixes += ["id.dropped"] * (len(ids) - len(known))
    if not lines:
        return o, fixes
    for x in violations:
        i = _line_index(x.where)
        if i is None or i >= len(lines) or not isinstance(lines[i], dict) or not isinstance(lines[i].get("text"), str):
            continue
        t = lines[i]["text"]
        if x.code == "say.empty":                   # an empty speech line becomes narration: 「发光石头一声不吭。」
            name = ctx.content.display_name(lines[i].get("who") if isinstance(lines[i].get("who"), str) else "",
                                            _guest_name(ctx.bible))
            lines[i] = {"k": "narr", "text": f"{name or '大家'}一声不吭。"}
            fixes.append(x.code)
            continue
        if x.code == "narr.sfx":
            lines[i]["k"] = "sfx"
            fixes.append(x.code)
            continue
        if x.code == "voice.narr_an":
            new = narr_voice(t, ctx.content.name("xionger"))
        elif x.code == "voice.jiji_wo":
            new = JIJI_WO.sub("本王", t)
        elif x.code == "voice.an":
            new = t.replace("俺们", "我们").replace("俺", "我")
        elif x.code == "voice.benwang":
            new = t.replace("本王", "我")
        elif x.code == "voice.xionger_wo":
            new = t.replace("我们", "俺们").replace("我", "俺")
        elif x.code == "script.latin":
            new = tu.strip_latin(t) if tu.cjk_len(tu.strip_latin(t)) >= 2 else t
        elif x.code == "script.digit":
            new = tu.digits_to_chinese(t)
        elif x.code == "script.emoji":
            new = tu.strip_emoji(t)
        elif x.code == "quote.unmatched":
            new = tu.drop_stray_quotes(t)
            if lines[i].get("k") == "say":                  # “…”” → “…” → …: the card adds its own pair
                new = tu.strip_outer_quotes(new)
            if not new.strip():                             # a lone quote: never an empty line (schema.line is hard)
                continue
        else:
            continue
        if new != t:
            lines[i]["text"] = new
            fixes.append(x.code)
    art = o.get("art")
    for code, key in (("safety.word", "safety"), ("adult.word", "adult")):    # fixed replacements, on every line
        if any(x.code == code for x in violations):                          # and in the picture brief (R2CHK-1)
            changed = False
            fields = [(l, "text") for l in lines if isinstance(l, dict)]
            if isinstance(art, dict):                                          # every text of the brief (_art_parts)
                fields += [(art, k) for k in ART_TEXT]
                fields += [(w, k) for w in _list(art.get("who")) if isinstance(w, dict) for k in WHO_TEXT]
            for d, k in fields:
                if isinstance(d.get(k), str):
                    t = swap_words(d[k], ctx.content, key)
                    changed = changed or t != d[k]
                    d[k] = t
            if changed:
                fixes.append(code)
    if isinstance(art, dict) and any(x.code == "art.speaker" for x in violations):
        gone = _unseen_speakers(art, lines)                  # they speak from outside the picture: no repair needed
        if gone:
            art["offscreen"] = [x for x in _list(art.get("offscreen")) if isinstance(x, str)] + gone
            fixes.append("art.speaker")
    two = sorted({i for x in violations if x.code == "narr.two" for i in [_line_index(x.where)] if i is not None},
                 reverse=True)
    for i in two:                                   # two sentences, two lines (last first: the indices shift)
        halves = _two_sentences(lines[i].get("text", "")) if i < len(lines) and isinstance(lines[i], dict) else []
        if halves and lines[i].get("k") == "narr":
            lines[i:i + 1] = [{"k": "narr", "text": h} for h in halves]
            fixes.append("narr.two")
    protected = _protected(o, ctx)
    subs = ctx.content.phrases.get("soft_fix_substitutions", {})
    flagged = {var for x in violations if x.code == "tierB" for var in x.data.get("variants", [])}
    if flagged:
        for i, l in enumerate(lines):
            if i in protected or not isinstance(l, dict) or not isinstance(l.get("text"), str):
                continue
            t = l["text"]
            for old in sorted(subs, key=len, reverse=True):     # 得紧紧的 holds 紧紧: its own replacement first
                if any(f in old or old in f for f in flagged):
                    t = t.replace(old, subs[old])
            if t != l["text"]:
                l["text"] = t
                fixes.append("tierB")
    if any(x.code == "sudden" for x in violations):
        for i, l in enumerate(lines):
            if i in protected or not isinstance(l, dict) or not isinstance(l.get("text"), str):
                continue
            t = l["text"]
            for w in ctx.content.phrases.get("sudden_strip", []):
                if t.startswith(w) and tu.cjk_len(t[len(w):]) >= 2:
                    t = t[len(w):]
                    break
            if t != l["text"]:
                l["text"] = t
                fixes.append("sudden")
    return o, fixes


def _script_fix(s: str) -> str:
    """The page's mechanical script fixes for one fork string: digits as 汉字, emoji dropped, Latin dropped only when
    at least two CJK characters remain (else fork.script asks for a repair)."""
    s = tu.strip_emoji(tu.digits_to_chinese(s))
    t = tu.strip_latin(s)
    return t if tu.cjk_len(t) >= 2 else s


def _as_question(q: str) -> str:
    """A fork question that is a statement (「权杖卡树上，吉吉晕头转向」) gets 「，怎么办？」 — or 「？」 alone when it ends with a
    question word or its last clause asks (ASKS: 「谁来破这个局」); trailing punctuation and dashes go first. When the tail
    would take it past fifteen 字, a clause that only says 「find a way」 goes and the clauses that tell the situation,
    from the end, take the tail (r1 003 「树根要踩碎海螺，得赶紧想办法」 → 「树根要踩碎海螺，怎么办？」); a statement that still does not
    fit stays without a question mark (fork.q_ask asks for one repair). A question with ？ anywhere stays as it is, and so
    does a q without two CJK characters (fork.script asks for its repair)."""
    if not q or "？" in q or "?" in q:
        return q
    t = q.rstrip("。！!…~～，,、；;：:—–－- ")
    if tu.cjk_len(t) < 2:
        return q
    if t.endswith(QUESTION_END) or ASKS.search(t):
        return t + "？"
    if tu.cjk_len(t + Q_TAIL) <= 15:
        return t + Q_TAIL
    told = [c for c in CLAUSE.split(t) if tu.cjk_len(c) >= 2 and not HOWTO.search(c)]
    for k in range(len(told)):
        if tu.cjk_len("，".join(told[k:]) + Q_TAIL) <= 15:
            return "，".join(told[k:]) + Q_TAIL
    return t


def last_question(obj: dict) -> dict:
    """A fork whose q is still a statement after its repair (fork.q_ask) gets a bare 「？」 (q.question): the banner never
    reads a statement. Pure; any other fork comes back as it is."""
    q = obj.get("q") if isinstance(obj, dict) else None
    if not isinstance(q, str) or not q.strip() or "？" in q or "?" in q or tu.cjk_len(q) < 2:
        return obj
    o = copy.deepcopy(obj)
    o["q"] = q.rstrip("。！!…~～，,、；;：:—–－- ") + "？"
    meta = o.get("_meta") if isinstance(o.get("_meta"), dict) else {}
    o["_meta"] = dict(meta, fixes=list(meta.get("fixes", [])) + ["q.question"])
    return o


def _swap_choice(o: dict, content: Content, key: str) -> bool:
    """The fixed replacements of one list made in place on a fork's q, option texts, hints and tokens and its idea
    chips; True when something changed."""
    changed = False
    if isinstance(o.get("q"), str):
        t = swap_words(o["q"], content, key)
        changed, o["q"] = changed or t != o["q"], t
    for x in _list(o.get("opts")):
        for k in ("text", "hint", "token"):
            if isinstance(x, dict) and isinstance(x.get(k), str):
                t = swap_words(x[k], content, key)
                changed, x[k] = changed or t != x[k], t
    if isinstance(o.get("ideas"), list):
        new = [swap_words(x, content, key) if isinstance(x, str) else x for x in o["ideas"]]
        changed, o["ideas"] = changed or new != o["ideas"], new
    return changed


def soft_fix_choice(obj: dict, content: Content | None = None) -> dict:
    """q and every option's text, hint and token as strings (first_str: a list's first string, anything else ""), ids
    A–C, distinct kinds, short idea chips and the page's script fixes for those strings (they are shown or quoted to
    later writers); a statement q made a question (q.question). With content, the fixed replacements of the safety and
    adult lists are made on every string (safety.word, adult.word) and an idea chip with a display problem
    (check_strings) is dropped, since the child may tap it. The fixes made are in `_meta.fixes` (never sent back to the
    model)."""
    o = copy.deepcopy(obj)
    fixes: list[str] = []
    o["q"] = first_str(o.get("q"))                     # strings only, never a repr (R3-ROB-3): no q is fork.q, no
    for x in _list(o.get("opts")):                     # option text the hard fork.opt_empty
        for k in ("text", "hint", "token") if isinstance(x, dict) else ():
            x[k] = first_str(x.get(k))
    if content is not None:                            # the fixed replacements (捂死 → 捂紧, 必定 → 一定) on every string
        for code, key in (("safety.word", "safety"), ("adult.word", "adult")):
            if _swap_choice(o, content, key):
                fixes.append(code)
    o["q"] = _script_fix(o["q"].strip())
    asked = _as_question(o["q"])
    if asked != o["q"]:
        o["q"] = asked
        fixes.append("q.question")
    o["_meta"] = {"fixes": fixes}
    opts = [x for x in _list(o.get("opts")) if isinstance(x, dict)][:3]
    used = [x.get("kind") for x in opts if x.get("kind") in OPTION_KINDS]
    missing = [k for k in OPTION_KINDS if k not in used]
    seen = set()
    for idx, x in enumerate(opts):
        x["id"] = "ABC"[idx]
        x["text"] = _script_fix(tu.normalize_quotes(x["text"].strip()))
        for k in ("hint", "token"):
            x[k] = _script_fix(x[k].strip())
        if x.get("kind") not in OPTION_KINDS or x.get("kind") in seen:
            x["kind"] = missing.pop(0) if missing else "careful"
        seen.add(x["kind"])
    o["opts"] = opts
    ideas = [str(x).strip() for x in _list(o.get("ideas")) if isinstance(x, str) and str(x).strip()]
    if content is not None:
        ideas = [x for x in ideas if not check_strings([x], content)]
    o["ideas"] = [c for c in (_chip(x) for x in ideas) if c][:2]
    return o


def _chip(x: str) -> str:
    """An idea chip of ten 字 at most: a longer one keeps its first clause when that fits, else it goes — a chip cut
    mid-phrase put half a sentence in the child's input box (r1 「大家一起大声唱歌盖住」)."""
    if tu.cjk_len(x) <= 10:
        return x
    head = CLAUSE.split(x)[0].strip()
    return head if 2 <= tu.cjk_len(head) <= 10 else ""


def count_usage(obj: dict, ctx: PageCtx) -> dict[str, int]:
    lines = _lines(obj)
    page, c = _text(lines), ctx.content
    out: dict[str, int] = {}
    for g in c.tier_b():
        n = _count_any(page, g["variants"])
        if n:
            out["tierb:" + g["key"]] = n
    ns = len(SUDDEN.findall(page))
    if ns:
        out[f"sudden:{ctx.chapter}"] = ns
    nq = sum(1 for l in lines if isinstance(l, dict) and l.get("k") == "narr"
             and NARR_QUESTION.search(str(l.get("text", "")).strip()))
    if nq:
        out["narr_q"] = nq
    for l in lines:
        if not isinstance(l, dict) or l.get("k") != "say" or not isinstance(l.get("text"), str):
            continue
        who, text = l.get("who"), l["text"]
        if not isinstance(who, str):
            continue
        if who == "xiongda" and "俺们" in text:
            out["xiongda_anmen"] = out.get("xiongda_anmen", 0) + text.count("俺们")
        if who in c.characters:
            for tic in c.tics(who):
                core = tu.cjk_only(tic["text"])
                if core and core in tu.cjk_only(text):
                    out["tic:" + core] = out.get("tic:" + core, 0) + 1
    d = obj.get("delta") if isinstance(obj.get("delta"), dict) else {}
    if d.get("rule_used") is True:
        out["rule_uses"] = 1
    refrain = tu.cjk_only(str(getattr(ctx.bible, "refrain", "") or ""))
    if len(refrain) >= 2 and any(isinstance(l, dict) and refrain in tu.cjk_only(str(l.get("text", ""))) for l in lines):
        out["refrain"] = 1              # the state block says how often it was heard (M3 r2, findings #13 fix 3)
    return out


def count_fork_usage(obj: dict) -> dict[str, int]:
    opts = [o for o in _list(obj.get("opts")) if isinstance(o, dict)] if isinstance(obj, dict) else []
    n = sum(1 for o in opts if PASSIVE.match(first_str(o.get("text"))))
    return {"passive_opts": n} if n else {}


# ---------------------------------------------------------------- the lean profile (M3 r3, plan item 4)
def _canon_id(content: Content, x: str) -> str | None:
    """A canon id (main or minor) from an id, a name or an alias (熊大, 强哥), or a main character's id with a suffix the
    model made up for a copy (xiongda_copy, xiongda2: M3 r2 #6's rule, _cast_id); None for anything else."""
    if x in content.characters or x in content.minor:
        return x
    named = next((cid for cid in list(content.characters) + list(content.minor) if x in content.names(cid)), None)
    return named or _cast_id(content, x)


def lean_who(content: Content, bible: BiblePublic, x) -> str | None:
    """A speaker or an art.who id as the page can carry it: a canon id (a name or an alias is its id), or "guest" for
    the book's guest — its name, "guest" or an id the content does not know (the model's own id for it) — when the book
    has one; None for nobody the book knows. A list gives its first string."""
    if isinstance(x, list):
        x = next((y for y in x if isinstance(y, str)), None)
    if not isinstance(x, str) or not x.strip():
        return None
    x = x.strip()
    cid = _canon_id(content, x)
    if cid:
        return cid
    guest = _guest_name(bible)
    return "guest" if guest and (x in ("guest", guest) or ASCII_ID.match(x)) else None


def lean_fix_page(obj, ctx: PageCtx) -> tuple:
    """The lean writer's code fixes of a page's shape and of who is on it (M3 r3, plan item 4), never a repair call:
    - a line that is no object or has no text goes (schema.line); a line with text but no known k is a say line when it
      has a who, else narration;
    - a speaker is read with lean_who; one nobody can be read from speaks in narration: 「松鼠说：“…”」 with the name the
      model wrote, the bare quote when there is none to read (an id, "guest" in a book without a guest) (id.speaker);
    - art.who is read the same way: an entry nobody can be read from leaves the picture brief (id.art); 李老板 is only
      ever on the phone (offscreen, art.libanban);
    - a canon character outside this world line's cast (bible.cast and state.cast_extra) who speaks, is drawn or is
      named in the text joins the line: the cameos, in that order, go into state.cast_extra when the page is kept
      (book_ops.join_cast). A canon character is never written as the guest: the guest id stays the book's guest's;
    - what later requests quote back (M3 r3 review, R3-SAFE-2): every text of the picture brief (ART_TEXT, WHO_TEXT) is a
      string, "" for any other shape (schema.art: a list focus skipped every check); the sum is "" when it is no string
      (schema.sum) or has a safety hit (safety.sum: 「光头强用猎枪打熊」); the delta keeps its own fields only, its lists
      holding strings without a safety hit (schema.delta, safety.delta: 「一把匕首」), rule_used only as true or false.
    Returns (page, fixes, cameos); the page is normalised (normalize_page). Pure."""
    o = normalize_page(obj) if isinstance(obj, dict) else obj
    if not isinstance(o, dict) or not isinstance(o.get("lines"), list):
        return o, [], []
    c, b = ctx.content, ctx.bible
    on_line = _cast(ctx)
    fixes: list[str] = []
    cameos: list[str] = []

    def meet(cid: str) -> None:
        if cid in c.characters and cid not in on_line and cid not in cameos:
            cameos.append(cid)

    lines = []
    for l in o["lines"]:
        if not isinstance(l, dict) or not isinstance(l.get("text"), str) or not l["text"].strip():
            fixes.append("schema.line")
            continue
        l = dict(l)
        if l.get("k") not in ("narr", "say", "sfx"):
            l["k"] = "say" if l.get("who") else "narr"
            fixes.append("schema.line")
        if l["k"] != "say":
            l.pop("who", None)
        else:
            who = lean_who(c, b, l.get("who"))
            if who is None:
                raw = l.get("who").strip() if isinstance(l.get("who"), str) else ""
                name = raw if tu.cjk_len(raw) and not ASCII_ID.match(raw) else ""
                said = tu.strip_outer_quotes(l["text"])
                l = {"k": "narr", "text": f"{name}说：“{said}”" if name else f"“{said}”"}
                fixes.append("id.speaker")
            else:
                if who != l.get("who"):
                    l["who"] = who
                    fixes.append("id.speaker")
                meet(who)
        lines.append(l)
    o["lines"] = lines
    art = o.get("art")
    if isinstance(art, dict):
        for k in ART_TEXT:
            if k in art and not isinstance(art[k], str):
                art[k] = ""
                fixes.append("schema.art")
        for w in _list(art.get("who")):
            for k in WHO_TEXT if isinstance(w, dict) else ():
                if k in w and not isinstance(w[k], str):
                    w[k] = ""
                    fixes.append("schema.art")
    if isinstance(art, dict) and isinstance(art.get("who"), list):
        ok = on_line | ({"guest"} if b.has_guest() else set()) | {"dongdongyao"}
        off = [x for x in _list(art.get("offscreen")) if isinstance(x, str)]
        drawn = []
        for w in art["who"]:
            cid = lean_who(c, b, w.get("id")) if isinstance(w, dict) else None
            if cid == "libanban":
                off += [] if "libanban" in off else ["libanban"]
                fixes.append("art.libanban")
                continue
            if cid is None or not (cid in ok or cid in c.characters):
                fixes.append("id.art")
                continue
            if cid != w.get("id"):
                fixes.append("id.art")
            meet(cid)
            drawn.append(dict(w, id=cid))
        art["who"] = drawn
        if "offscreen" in art or off:
            art["offscreen"] = off
    text = _text(lines)
    for cid in c.characters:
        if cid not in on_line and mentions(c, b, cid, text):
            meet(cid)
    fixes += _lean_quoted(o, c)
    return o, list(dict.fromkeys(fixes)), cameos


def _unsafe_text(s: str, content: Content) -> bool:
    return bool(_hits(content.safety_hard(), s) or _hits(content.safety_soft(), s))


def _lean_quoted(o: dict, content: Content) -> list[str]:
    """The sum and the delta of a lean page as later requests quote them (lean_fix_page), in place; the fixes made."""
    fixes: list[str] = []
    if "sum" in o and (not isinstance(o["sum"], str) or _unsafe_text(o["sum"], content)):
        fixes.append("schema.sum" if not isinstance(o["sum"], str) else "safety.sum")
        o["sum"] = ""
    d = o.get("delta")
    if "delta" in o and not isinstance(d, dict):
        o["delta"], d = {}, {}
        fixes.append("schema.delta")
    if not isinstance(d, dict):
        return fixes
    for k in list(d):
        if k not in DELTA_LISTS + ("rule_used",) or (k == "rule_used" and not isinstance(d[k], bool)):
            del d[k]
            fixes.append("schema.delta")
        elif k in DELTA_LISTS:
            kept = [x for x in as_list(d[k]) if isinstance(x, str)]
            fixes += ["schema.delta"] if len(kept) < len(as_list(d[k])) else []
            safe = [x for x in kept if not _unsafe_text(x, content)]
            fixes += ["safety.delta"] if len(safe) < len(kept) else []
            d[k] = safe
    return fixes


def lean_ctx(ctx: PageCtx, cameos) -> PageCtx:
    """ctx with the page's cameos on the world line (in a copy of its state): what a lean page is checked against."""
    if not cameos:
        return ctx
    state = ctx.state.copy()
    state.cast_extra = list(state.cast_extra) + [x for x in cameos if x not in state.cast_extra]
    return dataclasses.replace(ctx, state=state)


def _unreadable(text) -> bool:
    """A line nobody can read out after the code fixes: empty (strip_emoji left nothing of 「💥💥」) or with Latin letters
    left (strip_latin keeps them when fewer than two 汉字 would remain: 「Zzz……」)."""
    return not isinstance(text, str) or not text.strip() or (tu.has_latin(text) and tu.cjk_len(tu.strip_latin(text)) < 2)


def lean_check_page(obj, ctx: PageCtx, mechanical=MECHANICAL) -> tuple:
    """A lean page (M3 r3 item 4): lean_fix_page, the page's checks against the world line with its cameos, and every
    code fix those checks allow (soft_fix_page for the `mechanical` codes); a line those fixes leave unreadable — empty
    or with Latin letters left — goes (script.dropped, M3 r3 review R3-ROB-5: it shipped as 「Zzz……」, or as an empty
    line that dropped the page). Returns (page, violations left, fixes, cameos). What is left is the writer's to judge:
    a LEAN_SAFETY hit gets one repair, any other code stays a residual (a hard one — no line left — drops the page).
    Pure."""
    o, fixes, cameos = lean_fix_page(obj, ctx)
    cctx = lean_ctx(ctx, cameos)
    vs = validate_page(o, cctx)
    todo = [v for v in vs if v.code in mechanical]
    if todo:
        o, more = soft_fix_page(o, todo, cctx)
        fixes += [x for x in more if x not in fixes]
        vs = validate_page(o, cctx)
    lines = _lines(o)
    kept = [l for l in lines if not (isinstance(l, dict) and _unreadable(l.get("text")))]
    if len(kept) < len(lines):
        o["lines"] = kept
        fixes.append("script.dropped")
        vs = validate_page(o, cctx)
    return o, vs, fixes, cameos


HEAD_TEXT = ("title", "logline", "want")


def _head_text(s, content: Content) -> str:
    """A head text with the page's script fixes and the fixed replacements of the safety and adult lists; "" when Latin
    letters are left (fewer than two 汉字 without them: 「The Sneezing Cloud」, M3 r3 review R3-ROB-5) — the title is then
    the card's, a guest's name no guest, a place gone."""
    t = swap_words(_script_fix(s.strip()), content) if isinstance(s, str) else ""
    return "" if tu.has_latin(t) else t


def fix_head(obj, content: Content, card: dict | None = None) -> dict:
    """The lean writer's extended title line (M3 r3 item 2) with its shapes and words fixed in code, never a call: its
    fields only — title, logline and want as texts (_head_text); hero and cast as canon ids (_fix_cast: names and
    made-up copies read as ids, the hero first, four at most), the card's cast when fewer than two are left, and the
    first of the cast as the hero when the hero is not in it; guest {name, look} — a bare name is its name, while an id,
    a canon character's name (a canon character is never the guest) or another shape is no guest; places one to three
    texts. Pure."""
    o = copy.deepcopy(obj) if isinstance(obj, dict) else {}
    out = {"type": "title", **{k: _head_text(o.get(k), content) for k in ("title", "logline")}}
    if not isinstance(o.get("cast"), (list, str)):
        o["cast"] = []
    _fix_cast(o, content)
    cast = [x for x in _list(o.get("cast")) if isinstance(x, str)]
    if len(cast) < 2:
        cast = [x for x in (card or {}).get("cast", []) if x in content.characters][:4]
    hero = o.get("hero") if o.get("hero") in cast else (cast[0] if cast else "")
    out.update(hero=hero, cast=cast)
    g = o.get("guest")
    name, look = (g.get("name"), g.get("look")) if isinstance(g, dict) else (g, "")
    name = _head_text(name, content)
    if not name or ASCII_ID.match(name) or _canon_id(content, name):
        name = ""
    out["guest"] = {"name": name, "look": _head_text(look, content) if name else ""}
    places = [_head_text(x, content) for x in as_list(o.get("places")) if isinstance(x, str)]
    out["places"] = [x for x in places if x][:3]
    out["want"] = _head_text(o.get("want"), content)
    return out


def _head_parts(obj: dict) -> list[tuple[str, str]]:
    """(field, text) for every text of a lean head that is shown or quoted to the writer."""
    g = obj.get("guest") if isinstance(obj.get("guest"), dict) else {}
    out = [(k, obj.get(k)) for k in HEAD_TEXT] + [("guest", g.get("name")), ("guest", g.get("look"))]
    out += [("places", x) for x in _list(obj.get("places"))]
    return [(k, t) for k, t in out if isinstance(t, str) and t.strip()]


def validate_head(obj, content: Content) -> list[Violation]:
    """A lean head after fix_head: no title is hard (title.missing); a safety hit in any of its texts is safety (hard)
    or safety.soft — the writer's one repair (LEAN_SAFETY) — and any other display problem (check_strings) is
    head.text, a residual, like a title over twelve 字 (title.len). Messages name the field, for the repair prompt."""
    v = _Acc()
    if not isinstance(obj, dict) or not isinstance(obj.get("title"), str) or not obj["title"].strip():
        v.add("title.missing", HARD, "title", "第一行要有书名 title（十二字以内）。")
        return v
    if tu.cjk_len(obj["title"]) > 12:                  # the cover and the shelf (validate_title's limit; R3-ROB-6)
        v.add("title.len", SOFT, "title", "书名十二个字以内。")
    found: dict[str, list[str]] = {}
    for k, t in _head_parts(obj):
        for code in check_strings([t], content):
            found.setdefault(code, [])
            if k not in found[code]:
                found[code].append(k)
    if "safety" in found:
        v.add("safety", HARD, "title", "、".join(found["safety"]) + " 里有不适合小朋友的内容，请换掉。", fields=found["safety"])
    if "safety.soft" in found:
        v.add("safety.soft", SOFT, "title", "、".join(found["safety.soft"]) + " 里有小朋友可能模仿的危险行为或不该说的话，"
                                                                            "请换成安全、温和的说法。", fields=found["safety.soft"])
    rest = sorted(x for x in found if x not in ("safety", "safety.soft"))
    if rest:
        v.add("head.text", SOFT, "title", f"书名和设定里不要出现{_problems(rest)}。", problems=rest)
    return v


def drop_head_parts(obj: dict, content: Content, card: dict | None = None) -> dict:
    """A lean head that keeps a hard safety hit after its repair loses those parts (M3 r3 item 4: drop, never ship): the
    title becomes the card's, the logline or want goes empty, a guest with one goes, and so does such a place. Pure."""
    o = copy.deepcopy(obj)

    def bad(t) -> bool:
        return isinstance(t, str) and "safety" in check_strings([t], content)

    if bad(o.get("title")):
        o["title"] = str((card or {}).get("title") or "")
    for k in ("logline", "want"):
        if bad(o.get(k)):
            o[k] = ""
    g = o.get("guest") if isinstance(o.get("guest"), dict) else {}
    if bad(g.get("name")) or bad(g.get("look")):
        o["guest"] = {"name": "", "look": ""}
    o["places"] = [x for x in _list(o.get("places")) if not bad(x)]
    return o
