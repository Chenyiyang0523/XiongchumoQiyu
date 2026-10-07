"""Small, pure text helpers for Chinese picture-book pages."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

CJK = re.compile(r"[一-鿿]")
LATIN = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]+")
DIGIT = re.compile(r"[0-9０-９]")
# Emoji: the pictograph blocks (U+1F000–U+1FAFF), the misc symbols and dingbats (U+2600–U+27BF), the other characters
# with the Unicode Emoji property outside the CJK blocks (© ® ‼ ⁉ ™ ℹ ↔–↙ ↩ ↪ ⌚ ⌛ ⌨ ⏏ ⏩–⏳ ⏸–⏺ Ⓜ ▪ ▫ ▶ ◀ ◻–◾ ⤴ ⤵
# ⬅–⬇ ⬛ ⬜ ⭐ ⭕), and the invisible parts of emoji sequences (VS16 and VS15, ZWJ, the keycap mark, and the tag
# characters U+E0020–U+E007F that spell a subdivision flag such as Scotland's), so stripping an emoji leaves nothing
# behind. Written as escapes: the invisible ones cannot be seen in the source. CJK punctuation and
# the symbols of story text (…… —— ～ · → ①) are not in it.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u00A9\u00AE\u203C\u2049\u2122\u2139\u2194-\u2199"
                   "\u21A9\u21AA\u231A\u231B\u2328\u23CF\u23E9-\u23F3\u23F8-\u23FA\u24C2\u25AA\u25AB\u25B6\u25C0"
                   "\u25FB-\u25FE\u2934\u2935\u2B05-\u2B07\u2B1B\u2B1C\u2B50\u2B55\uFE0F\u200D\u20E3\uFE0E"
                   "\U000E0020-\U000E007F]")
_SENT = re.compile(r"(?<=[。！？!?；…])(?![。！？!?；…”’」』）)])")
# What a word can be drawn out or broken up with between two 汉字 (「笨——蛋」, 「闭～嘴」, 「笨…蛋」, 「笨 蛋」, a zero-width
# space): white space and the invisible format characters and fillers, dashes, tildes, ellipses (… is ... after NFKC),
# middle dots and bullets, the prolonged sound mark, asterisks and underscores. Sentence marks (。！？，、) are not in it.
# Written as escapes: most of these cannot be told apart, or seen, in the source (M3 r3 review, R3-SAFE-1).
STRETCH = re.compile("(?<=[\u4e00-\u9fff])[\\s\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f"
                     "\u202a-\u202e\u2060-\u206f\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0\U000e0000-\U000e0fff"
                     "\u2010-\u2015\u2e3a\u2e3b\u301c\u3030\u30fc\uff0d\\-~\uff5e\u223c\u2025\u2026\u22ef.\uff0e"
                     "\u00b7\u2022\u2027\u2219\u30fb\uff65*\uff0a_\uff3f]+(?=[\u4e00-\u9fff])")
_FULL_MARKS = str.maketrans({"!": "！", "?": "？", ",": "，", ";": "；", ":": "："})

STOP_BIGRAMS = frozenset("""起来 一下 看看 什么 我们 他们 你们 大家 一个 没有 这个 那个 自己 已经 还是 就是 可是 但是 然后 时候
知道 出来 下来 过来 回来 上去 下去 不是 怎么 这样 那样 一样 一起 东西 地方 这里 那里 现在 马上 一点 有点 真的 好像
突然 忽然 不要 可以 我的 你的 他的 俺的 一边 两个 三个 开始 终于 不过 还有 只是 因为 所以 如果 一声 一口 一眼""".split())


def cjk_len(s: str) -> int:
    return len(CJK.findall(s or ""))


def cjk_only(s: str) -> str:
    return "".join(CJK.findall(s or ""))


def split_sentences(s: str) -> list[str]:
    return [p.strip() for p in _SENT.split(s or "") if p.strip()]


def has_latin(s: str) -> bool:
    return bool(LATIN.search(s or ""))


def has_digit(s: str) -> bool:
    return bool(DIGIT.search(s or ""))


def has_emoji(s: str) -> bool:
    return bool(EMOJI.search(s or ""))


def strip_latin(s: str) -> str:
    return re.sub(r"\s*" + LATIN.pattern + r"\s*", "", s or "")


def strip_emoji(s: str) -> str:
    return EMOJI.sub("", s or "")


def fold(s: str) -> str:
    """`s` as the safety lists read it besides the text itself (M3 r3 review, R3-SAFE-1): compatibility forms folded
    (NFKC, with the sentence marks it makes half-width put back full-width, so 「！」 still ends a clause for a pattern)
    and the STRETCH marks between two 汉字 taken out — 「大——笨——蛋！」 → 「大笨蛋！」, 「阿——嚏！」 → 「阿嚏！」."""
    return STRETCH.sub("", unicodedata.normalize("NFKC", s or "").translate(_FULL_MARKS))


_CN = "零一二三四五六七八九"


def _num_cn(n: int) -> str:
    if n < 10:
        return _CN[n]
    if n < 20:
        return "十" + (_CN[n % 10] if n % 10 else "")
    if n < 100:
        return _CN[n // 10] + "十" + (_CN[n % 10] if n % 10 else "")
    if n == 100:
        return "一百"
    return "".join(_CN[int(c)] for c in str(n))


def digits_to_chinese(s: str) -> str:
    s = (s or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return re.sub(r"\d+", lambda m: _num_cn(int(m.group())), s)


def normalize_quotes(s: str) -> str:
    out, opening = [], True
    for ch in s or "":
        if ch == '"':
            out.append("“" if opening else "”")
            opening = not opening
        else:
            out.append(ch)
    return "".join(out)


def strip_outer_quotes(s: str) -> str:
    s = (s or "").strip()
    inner = s[1:-1]  # judge the inside, not the whole string: an ASCII quote opens and closes with one character
    for a, b in (("“", "”"), ("「", "」"), ('"', '"'), ("‘", "’"), ("『", "』")):
        if len(s) >= 2 and s.startswith(a) and s.endswith(b) and a not in inner and b not in inner:
            return inner.strip()
    return s


_PAIRS = (("“", "”"), ("「", "」"), ("『", "』"))


def drop_stray_quotes(s: str) -> str:
    """Quotes left unmatched at either end of a line, dropped: a closing ” 」 』 or an opening “ 「 『 whose kind has more
    of it than of its partner (谁把香蕉皮垫在底下了？！” → 谁把香蕉皮垫在底下了？！; matched pairs such as “松手” stay)."""
    t = (s or "").strip()
    changed = True
    while changed and t:
        changed = False
        for a, b in _PAIRS:
            for q, other in ((a, b), (b, a)):
                if t.count(q) > t.count(other) and (t.endswith(q) or t.startswith(q)):
                    t = (t[:-1] if t.endswith(q) else t[1:]).strip()
                    changed = True
    return t


def line_display(k: str, text: str, speaker: str | None) -> str:
    if k == "say" and speaker:
        return f"{speaker}：“{text}”"
    return text


def display_width(s: str) -> int:
    w = sum(0.5 if ord(ch) < 128 else 1.0 for ch in s or "")
    return int(-(-w // 1))


def card_rows(lines: list[tuple[str, str, str | None]], per_row: int = 28, sfx_weight: float = 1.2) -> float:
    rows = 0.0
    for k, text, speaker in lines:
        n = max(1, -(-display_width(line_display(k, text, speaker)) // per_row))
        rows += n * (sfx_weight if k == "sfx" else 1.0)
    return round(rows, 3)


def content_bigrams(s: str, remove: Iterable[str] = (), stop: frozenset = STOP_BIGRAMS,
                    function_chars: str = "") -> set[str]:
    s = s or ""
    for w in sorted({w for w in remove if w}, key=len, reverse=True):
        s = s.replace(w, "|")
    runs, cur = [], []
    for ch in s:
        if CJK.match(ch) and ch not in function_chars:
            cur.append(ch)
        elif cur:
            runs.append("".join(cur))
            cur = []
    if cur:
        runs.append("".join(cur))
    grams = set()
    for r in runs:
        for i in range(len(r) - 1):
            g = r[i:i + 2]
            if g not in stop:
                grams.add(g)
    return grams


def joined_bigrams(s: str, names: Iterable[str] = (), stop: frozenset = STOP_BIGRAMS, function_chars: str = "") -> set[str]:
    """Bigrams of consecutive content characters, read through function characters (隔着门 → 隔门; any other non-CJK
    character ends a run). Names are taken out as whole words: a bigram is dropped only when both its characters lie
    in occurrences of `names`, so 学雪兔叫 keeps 学雪 and 兔叫 for the name 雪兔 (content_bigrams' `remove` splits the
    text at a name and loses them)."""
    s = s or ""
    named: set[int] = set()
    for w in {w for w in names if isinstance(w, str) and w}:
        i = s.find(w)
        while i >= 0:
            named.update(range(i, i + len(w)))
            i = s.find(w, i + 1)
    grams: set[str] = set()
    prev = None
    for i, ch in enumerate(s):
        if not CJK.match(ch):
            prev = None
        elif ch not in function_chars:
            if prev is not None and not (prev in named and i in named) and s[prev] + ch not in stop:
                grams.add(s[prev] + ch)
            prev = i
    return grams


def copied_spans(text: str, sources: Iterable[str], n: int = 6) -> list[str]:
    t = cjk_only(text)
    if len(t) < n:
        return []
    windows: set[str] = set()
    for src in sources:
        s = cjk_only(src)
        windows.update(s[i:i + n] for i in range(len(s) - n + 1))
    hits = [i for i in range(len(t) - n + 1) if t[i:i + n] in windows]
    spans, start, prev = [], None, None
    for i in hits:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            spans.append(t[start:prev + n])
            start = prev = i
    if start is not None:
        spans.append(t[start:prev + n])
    return spans
