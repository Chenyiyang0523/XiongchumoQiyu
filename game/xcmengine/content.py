"""Loads and validates the authored content files in content/*.json."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import textutil as tu

FILES = ("characters", "phrases", "beats", "seeds", "examples", "places", "style")
_HERE = Path(__file__).resolve().parent / "content"


class Content:
    def __init__(self, root: str | Path | None = None):
        root = Path(root) if root else _HERE
        data = {}
        for name in FILES:
            with open(root / f"{name}.json", encoding="utf-8") as f:
                data[name] = json.load(f)
        ch = data["characters"]
        self.characters: dict = ch["characters"]
        self.minor: dict = ch.get("minor", {})
        self.eras: dict = ch.get("eras", {})
        self.phrases: dict = data["phrases"]
        self.beats: dict = data["beats"]
        self.seeds: dict = data["seeds"]
        self.examples: list[dict] = data["examples"]["pages"]
        self.places: list[dict] = data["places"]["places"]
        self.places_default: str = data["places"].get("default", "forest")
        self.backgrounds: dict = data["places"].get("backgrounds", {})
        self.style: dict = data["style"]
        self._tier_a = None
        self._safety = None

    # ---- names and ids -------------------------------------------------
    def name(self, cid: str) -> str:
        if not isinstance(cid, str):            # a model field of another shape (a list of two ids) names no one
            return ""
        if cid in self.characters:
            return self.characters[cid]["name"]
        if cid in self.minor:
            return self.minor[cid]["name"]
        return "客串" if cid == "guest" else cid

    def display_name(self, cid: str, guest_name: str = "") -> str:
        return guest_name if cid == "guest" and guest_name else self.name(cid)

    def names(self, cid: str) -> list[str]:
        """Every name the story text uses for a canon character: its name first, then its aliases (光头强, 强哥);
        [] for an unknown id."""
        card = self.characters.get(cid) or self.minor.get(cid) if isinstance(cid, str) else None
        if not card:
            return []
        aliases = card.get("aliases") if isinstance(card.get("aliases"), list) else []
        return [card["name"]] + [a for a in aliases if isinstance(a, str) and a and a != card["name"]]

    def false_friends(self, cid: str) -> list[str]:
        """Words that contain a character's name but are not about them (毛毛虫, 毛毛雨 for 毛毛)."""
        card = (self.characters.get(cid) or self.minor.get(cid) or {}) if isinstance(cid, str) else {}
        ff = card.get("false_friends") if isinstance(card.get("false_friends"), list) else []
        return [w for w in ff if isinstance(w, str) and w]

    def cast_ids(self) -> set[str]:
        return set(self.characters)

    def speaker_ids(self) -> set[str]:
        return set(self.characters) | set(self.minor)

    def card(self, card_id: str) -> dict:
        return next(c for c in self.seeds["cards"] if c["id"] == card_id)

    def tics(self, cid: str) -> list[dict]:
        return list(self.characters.get(cid, {}).get("tics", []))

    def sample_lines(self, cid: str) -> list[str]:
        return [re.sub(r"^\[[CV]\]\s*", "", s) for s in self.characters.get(cid, {}).get("samples", [])]

    def look(self, cid: str) -> str:
        if cid in self.characters:
            return self.characters[cid].get("look", "")
        return self.minor.get(cid, {}).get("look", "")

    # ---- phrases -------------------------------------------------------
    def function_chars(self) -> str:
        return self.phrases.get("function_chars", "")

    def tier_a(self) -> list[re.Pattern]:
        if self._tier_a is None:
            ta = self.phrases["tier_a"]
            self._tier_a = [re.compile(re.escape(w)) for w in ta["literal"]] + [re.compile(r) for r in ta["regex"]]
        return self._tier_a

    def tier_b(self) -> list[dict]:
        return [{"variants": g["variants"], "max_per_book": int(g["max_per_book"]), "key": g["variants"][0]}
                for g in self.phrases["tier_b"]]

    def _safety_compiled(self):
        if self._safety is None:
            s = self.phrases["safety"]
            self._safety = ([re.compile(p) for p in s["hard"]], [re.compile(p) for p in s["soft"]])
        return self._safety

    def safety_hard(self) -> list[re.Pattern]:
        return self._safety_compiled()[0]

    def safety_soft(self) -> list[re.Pattern]:
        return self._safety_compiled()[1]

    def opening_banned(self) -> re.Pattern:
        return re.compile(self.phrases["openings_banned_regex"])

    # ---- places and beats ----------------------------------------------
    def place_for(self, text: str) -> dict:
        for p in self.places:
            if any(k in (text or "") for k in p["keywords"]):
                return p
        return next(p for p in self.places if p["id"] == self.places_default)

    def structure(self, name: str) -> dict:
        return self.beats["structures"][name]

    def layout(self, length: str) -> list[tuple[int, str]]:
        spec = self.beats["lengths"][length]
        return list(zip(spec["chapters"], spec["roles"]))


@lru_cache(maxsize=4)
def _load(root: str) -> Content:
    return Content(root or None)


def load_content(root: str | Path | None = None) -> Content:
    return _load(str(root) if root else "")


def validate_content(c: Content) -> list[str]:
    problems: list[str] = []
    ids = c.cast_ids()
    for cid, card in c.characters.items():
        for key in ("name", "who", "speech", "self", "samples", "never", "look", "color"):
            if not card.get(key):
                problems.append(f"character {cid}: missing {key}")
        for t in card.get("tics", []):
            if not isinstance(t.get("max_per_book"), int):
                problems.append(f"character {cid}: tic without int max_per_book")
    for card in c.seeds.get("cards", []):
        if not set(card.get("cast", [])) <= ids:
            problems.append(f"card {card.get('id')}: unknown cast")
        if card.get("structure") not in c.beats["structures"]:
            problems.append(f"card {card.get('id')}: unknown structure")
    for length, spec in c.beats["lengths"].items():
        if len(spec["chapters"]) != len(spec["roles"]):
            problems.append(f"length {length}: chapters/roles mismatch")
        if spec["chapters"][-1] != 4 or spec["chapters"][-2] != 2:
            problems.append(f"length {length}: finale must be 4 pages after a 2-page chapter")
        for n, role in zip(spec["chapters"], spec["roles"]):
            if len(c.beats["tension"].get(role, [])) != n:
                problems.append(f"length {length}: tension for {role}")
            for name, st in c.beats["structures"].items():
                if len(st["roles"].get(role, [])) != n:
                    problems.append(f"structure {name}: role {role} needs {n} beats")
    for p in c.examples:
        text = "".join(l.get("text", "") for l in p.get("lines", []))
        if tu.cjk_len(text) > 80 or not 2 <= len(p.get("lines", [])) <= 5:
            problems.append(f"example {p.get('id')}: length")
    for p in c.places:
        if p.get("bg") not in c.backgrounds:
            problems.append(f"place {p.get('id')}: unknown background {p.get('bg')}")
    if c.places_default not in {p.get("id") for p in c.places}:
        problems.append(f"places: default {c.places_default} is not one of the places")
    else:  # place_for falls back to the default place, so it can only be asked once that exists
        # The first place with a keyword in the text wins, so a place whose own name holds a keyword of an earlier place
        # (or none of its own keywords) is never found: every place must come back when looked up by its own name.
        for p in c.places:
            found = c.place_for(p.get("name", ""))
            if found.get("id") != p.get("id"):
                problems.append(
                    f"place {p.get('id')}: its own name {p.get('name')!r} finds {found.get('id')}, not {p.get('id')}")
    for key in ("writer_system", "bible_system_extra", "repair_system", "idea_system", "premise_system",
                "gate_system", "image_style"):
        if not c.style.get(key):
            problems.append(f"style: missing {key}")
    return problems
