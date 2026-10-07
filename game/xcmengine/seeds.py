"""Seeded sampling of premise cards and story dimensions, plus cross-book novelty memory."""
from __future__ import annotations

import copy
import random
import re
from dataclasses import dataclass, field

from . import textutil as tu
from .content import Content

KEEP_BOOKS = 10
NOVELTY_DIMS = ("structure", "season", "weather", "guest_kind", "prop")
USED_BOOKS = 3          # the last books whose rule effect and prop a new card avoids (M3 r2 #17)
_RULE_CLAUSE = re.compile(r"[，,。；;！!？?、]")
_RULE_MODAL = re.compile(r"就|会|必须|必定|一定|要")
_RULE_SUBJECT = re.compile(r"^(所有人|每个人|大家|在场的人|周围的人|身边的人|谁|他们|它们|他|她|它)")
_RULE_FILLER = re.compile(r"^(得|都|也|还|总|马上|立刻|立马|一直|原地|全都)+")


def rule_effect(rule) -> str:
    """A book's rule effect in a few words for the cross-book memory (M3 r2 #17): the first clause of rule.effect after
    its modal (所有人必须原地转圈 → 转圈) or its subject, without leading adverbs (原地, 一直); "" when that is not two to
    ten 字. r1 001 and 002 both made everyone spin."""
    effect = rule.get("effect") if isinstance(rule, dict) else None
    if not isinstance(effect, str):
        return ""
    clause = _RULE_CLAUSE.split(effect.strip())[0]
    modals = list(_RULE_MODAL.finditer(clause))
    clause = clause[modals[-1].end():] if modals else _RULE_SUBJECT.sub("", clause)
    words = tu.cjk_only(_RULE_FILLER.sub("", clause))
    return words if 2 <= len(words) <= 10 else ""


@dataclass
class Memory:
    books: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"books": copy.deepcopy(self.books)}

    @classmethod
    def from_dict(cls, d) -> "Memory":
        books = [b for b in (d or {}).get("books", []) if isinstance(b, dict)]
        return cls(books=books[-KEEP_BOOKS:])

    def recent(self, n: int) -> list[dict]:
        return self.books[-n:] if n > 0 else []

    def phrases(self, last: int = 3) -> frozenset[str]:
        return frozenset(p for b in self.recent(last) for p in b.get("phrases", []))

    def families(self, last: int = 2) -> list[str]:
        return [b["family"] for b in self.recent(last) if b.get("family")]

    def used(self, last: int = USED_BOOKS) -> list[str]:
        """What the last books' rules did and the props they drew, most recent first, each once: a new card's bible
        prompt hears 「最近几本书用过：…」 (M3 r2 #17). A memory saved before round 2 has props only."""
        out: list[str] = []
        for b in reversed(self.recent(last)):
            for w in (b.get("rule"), (b.get("dims") or {}).get("prop")):
                if isinstance(w, str) and w and w not in out:
                    out.append(w)
        return out

    def remember(self, card_id: str, dims: dict, family: str = "", phrases=(), rule=None) -> None:
        """One finished book. `rule` is its bible.rule: its effect is kept in a few words (rule_effect)."""
        entry = {"card": card_id, "dims": dict(dims), "family": family, "phrases": sorted(set(phrases))}
        effect = rule_effect(rule)
        if effect:
            entry["rule"] = effect
        self.books.append(entry)
        self.books = self.books[-KEEP_BOOKS:]


def new_rng(seed_text: str) -> random.Random:
    return random.Random(seed_text)


def _differs(a: dict, b: dict) -> int:
    return sum(1 for k in NOVELTY_DIMS if a.get(k) != b.get(k))


def sample_dims(content: Content, rng: random.Random, memory: Memory, card: dict) -> dict:
    pools = content.seeds["dims"]
    recent_structs = [b.get("dims", {}).get("structure") for b in memory.recent(2)]
    if card.get("structure") in pools["structure"] and rng.random() < 0.6:
        structure = card["structure"]
    else:
        structure = rng.choice(pools["structure"])
    if structure in recent_structs:
        fresh = [s for s in pools["structure"] if s not in recent_structs]
        if fresh:
            structure = rng.choice(fresh)
    dims = {"tone": card.get("tone") or rng.choice(pools["tone"]), "structure": structure}
    used = {b.get("dims", {}).get("prop") for b in memory.recent(USED_BOOKS)}
    pool = dict(pools, prop=[p for p in pools["prop"] if p not in used] or pools["prop"])   # no prop of the last books
    for k in ("season", "time", "weather", "guest_kind", "prop"):
        dims[k] = rng.choice(pool[k])
    recent = [b.get("dims", {}) for b in memory.recent(3)]
    for _ in range(50):
        if all(_differs(dims, r) >= 2 for r in recent):
            break
        k = rng.choice(("season", "weather", "guest_kind", "prop"))
        dims[k] = rng.choice(pool[k])
    return dims


def draw_cards(content: Content, rng: random.Random, memory: Memory, n: int = 3, favorite: str | None = None,
               exclude=()) -> list[dict]:
    excluded = set(exclude)
    cards = [c for c in content.seeds["cards"] if c["id"] not in excluded]
    recent = {b.get("card") for b in memory.recent(KEEP_BOOKS)}
    pool = [c for c in cards if c["id"] not in recent] or cards
    weights = [4.0 if favorite and favorite in c["cast"] else 1.0 for c in pool]
    picked: list[dict] = []
    while pool and len(picked) < n:
        r, acc, idx = rng.random() * sum(weights), 0.0, len(pool) - 1
        for i, w in enumerate(weights):
            acc += w
            if r < acc:
                idx = i
                break
        card = copy.deepcopy(pool.pop(idx))
        weights.pop(idx)
        card["dims"] = sample_dims(content, rng, memory, card)
        if memory.used():
            card["avoid"] = memory.used()           # the card block's 「最近几本书用过：…」 (M3 r2 #17)
        picked.append(card)
    return picked


def pick_samples(content: Content, cast, rng: random.Random, k: int = 2) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for cid in cast:
        lines = content.sample_lines(cid)
        out[cid] = rng.sample(lines, min(k, len(lines))) if lines else []
    return out


def pick_exemplars(content: Content, rng: random.Random, k: int = 12) -> list[str]:
    by_beat: dict[str, list[str]] = {}
    for p in content.examples:
        by_beat.setdefault(p["beat"], []).append(p["id"])
    chosen = [rng.choice(ids) for _, ids in sorted(by_beat.items())]
    rest = [p["id"] for p in content.examples if p["id"] not in chosen]
    rng.shuffle(rest)
    return (chosen + rest)[:k]
