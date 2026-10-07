"""Story data model: plain dataclasses that round-trip through JSON-safe dicts."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, fields

SCHEMA_VERSION = 1
LENGTH_SIZES = {"short": [3, 2, 4], "medium": [3, 3, 2, 4], "long": [3, 3, 3, 2, 4]}


def _pick(cls, d) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: copy.deepcopy(v) for k, v in (d or {}).items() if k in names}


class _Simple:
    """Mixin for flat dataclasses whose fields are JSON values."""

    def to_dict(self):
        return copy.deepcopy(asdict(self))

    @classmethod
    def from_dict(cls, d):
        return cls(**_pick(cls, d if isinstance(d, dict) else {}))


@dataclass
class Line(_Simple):
    k: str
    text: str
    who: str | None = None


@dataclass
class ArtWho(_Simple):
    id: str
    act: str = ""
    face: str = ""


@dataclass
class ArtBrief:
    place: str = ""
    time: str = ""
    weather: str = ""
    shot: str = ""
    who: list[ArtWho] = field(default_factory=list)
    focus: str = ""
    mood: str = ""
    offscreen: list[str] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["who"] = [w.to_dict() for w in self.who]
        return d

    @classmethod
    def from_dict(cls, d):
        d = _pick(cls, d if isinstance(d, dict) else {})
        who, off = d.get("who"), d.get("offscreen")
        d["who"] = [ArtWho.from_dict(w) for w in (who if isinstance(who, list) else []) if isinstance(w, dict) and w.get("id")]
        d["offscreen"] = [x for x in (off if isinstance(off, list) else []) if isinstance(x, str)]
        return cls(**d)


@dataclass
class MediaRef(_Simple):
    state: str = "none"
    file: str = ""
    error: str = ""
    attempts: int = 0


@dataclass
class Page:
    id: str
    lines: list[Line]
    art: ArtBrief
    delta: dict = field(default_factory=dict)
    summary: str = ""
    image: MediaRef = field(default_factory=MediaRef)
    audio: list[MediaRef] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    stamp: str = ""

    def text(self) -> str:
        return "".join(l.text for l in self.lines)

    def speakers(self) -> set[str]:
        return {l.who for l in self.lines if l.k == "say" and l.who}

    def to_dict(self):
        return {"id": self.id, "lines": [l.to_dict() for l in self.lines], "art": self.art.to_dict(),
                "delta": copy.deepcopy(self.delta), "summary": self.summary, "image": self.image.to_dict(),
                "audio": [a.to_dict() for a in self.audio], "fixes": list(self.fixes), "stamp": self.stamp}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], lines=[Line.from_dict(x) for x in d.get("lines", []) if isinstance(x, dict)],
                   art=ArtBrief.from_dict(d.get("art", {})), delta=copy.deepcopy(d.get("delta", {})),
                   summary=d.get("summary", ""), image=MediaRef.from_dict(d.get("image", {})),
                   audio=[MediaRef.from_dict(a) for a in d.get("audio", [])], fixes=list(d.get("fixes", [])),
                   stamp=d.get("stamp", ""))


@dataclass
class Option(_Simple):
    id: str
    kind: str
    text: str
    hint: str = ""
    token: str = ""
    icon: str = ""
    cameo: str = ""         # a canon character this option brings into its world line (idea options)
    label: str = ""         # the child's cleaned words: for the screen only, never in prompts


@dataclass
class ChoicePoint:
    question: str
    options: list[Option]
    ideas: list[str] = field(default_factory=list)
    axis: str = ""
    fixes: list[str] = field(default_factory=list)          # mechanical fixes made in code (q.question)

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)

    def to_dict(self):
        return {"question": self.question, "options": [o.to_dict() for o in self.options],
                "ideas": list(self.ideas), "axis": self.axis, "fixes": list(self.fixes)}

    @classmethod
    def from_dict(cls, d):
        return cls(question=d.get("question", ""), options=[Option.from_dict(o) for o in d.get("options", [])],
                   ideas=list(d.get("ideas", [])), axis=d.get("axis", ""),
                   fixes=[x for x in d.get("fixes", []) if isinstance(x, str)] if isinstance(d.get("fixes"), list) else [])


@dataclass
class Ending(_Simple):
    title: str
    family: str
    recap: list[str] = field(default_factory=list)


@dataclass
class LedgerItem(_Simple):
    id: str
    kind: str
    what: str
    role: str = ""
    payoff: str = ""
    planted_page: str | None = None
    planted_text: str = ""
    due_chapter: int | None = None
    status: str = "planned"


@dataclass
class StoryState(_Simple):
    items: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    qualities: dict[str, int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    cast_extra: list[str] = field(default_factory=list)     # cameo characters on this world line (inherited)

    def copy(self) -> "StoryState":
        return StoryState.from_dict(self.to_dict())

    def count(self, key: str) -> int:
        return int(self.counters.get(key, 0))

    def bump(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.count(key) + n


@dataclass
class Node:
    id: str
    parent: str | None
    via: str | None
    chapter: int
    role: str = ""
    outcome: str = ""
    status: str = "pending"
    plan: str = ""
    pages: list[Page] = field(default_factory=list)
    choice: ChoicePoint | None = None
    ending: Ending | None = None
    state: StoryState = field(default_factory=StoryState)
    ledger: list[LedgerItem] = field(default_factory=list)
    choice_log: list[dict] = field(default_factory=list)
    error: str = ""
    error_kind: str = ""
    usage: dict = field(default_factory=dict)
    speculative: bool = False
    read: bool = False
    family: str = ""

    def to_dict(self):
        return {"id": self.id, "parent": self.parent, "via": self.via, "chapter": self.chapter, "role": self.role,
                "outcome": self.outcome, "status": self.status, "plan": self.plan,
                "pages": [p.to_dict() for p in self.pages],
                "choice": self.choice.to_dict() if self.choice else None,
                "ending": self.ending.to_dict() if self.ending else None,
                "state": self.state.to_dict(), "ledger": [x.to_dict() for x in self.ledger],
                "choice_log": copy.deepcopy(self.choice_log), "error": self.error, "error_kind": self.error_kind,
                "usage": copy.deepcopy(self.usage), "speculative": self.speculative, "read": self.read,
                "family": self.family}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], parent=d.get("parent"), via=d.get("via"), chapter=int(d.get("chapter", 1)),
                   role=d.get("role", ""), outcome=d.get("outcome", ""), status=d.get("status", "pending"),
                   plan=d.get("plan", ""), pages=[Page.from_dict(p) for p in d.get("pages", [])],
                   choice=ChoicePoint.from_dict(d["choice"]) if d.get("choice") else None,
                   ending=Ending.from_dict(d["ending"]) if d.get("ending") else None,
                   state=StoryState.from_dict(d.get("state", {})),
                   ledger=[LedgerItem.from_dict(x) for x in d.get("ledger", [])],
                   choice_log=copy.deepcopy(d.get("choice_log", [])), error=d.get("error", ""),
                   error_kind=d.get("error_kind", ""), usage=copy.deepcopy(d.get("usage", {})),
                   speculative=bool(d.get("speculative", False)), read=bool(d.get("read", False)),
                   family=d.get("family", ""))


@dataclass
class BiblePublic(_Simple):
    title: str = ""
    logline: str = ""
    hero: str = ""
    cast: list[str] = field(default_factory=list)
    era: str = "any"
    want: str = ""
    oddity: str = ""
    rule: dict = field(default_factory=dict)
    guest: dict = field(default_factory=dict)
    antagonist: dict = field(default_factory=dict)
    places: list[str] = field(default_factory=list)
    refrain: str = ""
    setups: list[dict] = field(default_factory=list)

    def setup(self, sid: str) -> dict | None:
        return next((s for s in self.setups if s.get("id") == sid), None)

    def turn_setup(self) -> dict | None:
        return next((s for s in self.setups if s.get("role") == "turn"), None)

    def has_guest(self) -> bool:
        return bool((self.guest or {}).get("name"))

    def title_line(self) -> dict:
        """The lean writer's extended title line of this bible (M3 r3 item 2; book_ops.head_lines makes the bible from
        it): the first line the lean prompts quote of the book so far."""
        g = self.guest if isinstance(self.guest, dict) else {}
        return {"type": "title", "title": self.title, "logline": self.logline, "hero": self.hero, "cast": list(self.cast),
                "guest": {"name": str(g.get("name") or ""), "look": str(g.get("look") or "")},
                "places": list(self.places), "want": self.want}


@dataclass
class BibleSecret(_Simple):
    payoffs: dict = field(default_factory=dict)
    twists: list[dict] = field(default_factory=list)
    endings: dict = field(default_factory=dict)
    twist_by_branch: dict = field(default_factory=dict)
    low: str = ""                   # what every low point loses or breaks, whichever way the child went (M3 r2 #8)


def child_id(node_id: str, option_id: str) -> str:
    return f"{node_id}.{option_id}"


def page_id(node_id: str, index: int) -> str:
    return f"{node_id}.p{index}"


def path_ids(node_id: str) -> list[str]:
    parts = node_id.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts) + 1)]


@dataclass
class Book:
    id: str
    length: str
    premise: dict
    seeds: dict
    bible: BiblePublic | None = None
    secret: BibleSecret | None = None
    status: str = "birth"
    error: str = ""
    nodes: dict[str, Node] = field(default_factory=dict)
    current: dict = field(default_factory=dict)
    cover: MediaRef = field(default_factory=MediaRef)
    endings_found: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    created: float = 0.0
    updated: float = 0.0
    schema: int = SCHEMA_VERSION
    samples: dict = field(default_factory=dict)
    exemplars: list[str] = field(default_factory=list)

    def path(self, node_id: str) -> list[Node]:
        return [self.nodes[i] for i in path_ids(node_id) if i in self.nodes]

    def pages_on_path(self, node_id: str) -> list[Page]:
        return [p for n in self.path(node_id) for p in n.pages]

    def chapter_sizes(self) -> list[int]:
        return list(LENGTH_SIZES[self.length])

    def chapters(self) -> int:
        return len(LENGTH_SIZES[self.length])

    def is_final_chapter(self, chapter: int) -> bool:
        return chapter >= self.chapters()

    def first_page_number(self, chapter: int) -> int:
        return 1 + sum(self.chapter_sizes()[:chapter - 1])

    def to_dict(self):
        return {"schema": self.schema, "id": self.id, "length": self.length,
                "premise": copy.deepcopy(self.premise), "seeds": copy.deepcopy(self.seeds),
                "bible": self.bible.to_dict() if self.bible else None,
                "secret": self.secret.to_dict() if self.secret else None,
                "status": self.status, "error": self.error,
                "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
                "current": copy.deepcopy(self.current), "cover": self.cover.to_dict(),
                "endings_found": copy.deepcopy(self.endings_found), "usage": copy.deepcopy(self.usage),
                "created": self.created, "updated": self.updated,
                "samples": copy.deepcopy(self.samples), "exemplars": list(self.exemplars)}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], length=d.get("length", "medium"), premise=copy.deepcopy(d.get("premise", {})),
                   seeds=copy.deepcopy(d.get("seeds", {})),
                   bible=BiblePublic.from_dict(d["bible"]) if d.get("bible") else None,
                   secret=BibleSecret.from_dict(d["secret"]) if d.get("secret") else None,
                   status=d.get("status", "birth"), error=d.get("error", ""),
                   nodes={k: Node.from_dict(v) for k, v in d.get("nodes", {}).items()},
                   current=copy.deepcopy(d.get("current", {})), cover=MediaRef.from_dict(d.get("cover", {})),
                   endings_found=copy.deepcopy(d.get("endings_found", [])), usage=copy.deepcopy(d.get("usage", {})),
                   created=float(d.get("created", 0.0)), updated=float(d.get("updated", 0.0)),
                   schema=int(d.get("schema", SCHEMA_VERSION)), samples=copy.deepcopy(d.get("samples", {})),
                   exemplars=list(d.get("exemplars", [])))
