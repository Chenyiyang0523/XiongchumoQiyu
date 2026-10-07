"""Ren'Py adapter for the unchanged Linux LeanWriter (see xcmengine/UPSTREAM.json).

Only input selection, transport address, serializable state and display conversion
live here. Prompts, chapter plans, line settling and continuation belong upstream.
"""
from __future__ import annotations

import copy

from xcmengine import book_ops, freetext, prompts
from xcmengine.config import Settings
from xcmengine.content import load_content
from xcmengine.lean import LeanWriter
from xcmengine.llm import ChatClient
from xcmengine.models import Book
from xcmengine.seeds import Memory, new_rng, sample_dims


def length_for(duration):
    return "short" if duration <= 5 else "medium" if duration <= 10 else "long"


def client_for(endpoint, token):
    if not endpoint.endswith("/chat/completions"):
        raise ValueError("Story endpoint must end in /chat/completions")
    # Empty env prevents unrelated API_BASE settings from bypassing the local relay.
    return ChatClient(Settings({"api_base": endpoint[:-len("/chat/completions")]}, env={}), api_key=token)


def card_for(scenario, seed, client):
    c = load_content()
    card = next((x for x in c.seeds["cards"] if scenario in (x["hook"], x["title"])), None)
    if card is None:
        return freetext.interpret_premise(c, client, scenario, seed=seed)
    card = copy.deepcopy(card)
    card["dims"] = sample_dims(c, new_rng(seed), Memory(), card)
    return card


def display(book, node):
    """Preserve every settled line and choice; only map backgrounds and names."""
    c = load_content()
    guest = book.bible.guest.get("name", "") if book.bible else ""
    segments, text = [], []
    for page in node.pages:
        scene = c.place_for(page.art.place)["bg"].removeprefix("bg_")
        if scene == "night":
            scene = "forest"
        segments.append(("scene", scene))
        text.append("【场景：" + scene + "】")
        for line in page.lines:
            if line.k == "say":
                name = c.display_name(line.who, guest)
                segments.append(("dialogue", name, line.text, None))
                text.append("**" + name + "**：" + line.text)
            else:
                segments.append(("narration" if line.k == "narr" else "text", line.text))
                text.append(line.text)
    options = [(o.id, o.text) for o in node.choice.options] if node.choice else []
    if options:
        text.append("**请选择：**")
        text.extend(oid + ". " + label for oid, label in options)
    if node.ending:
        text.append("【剧终】")
    return {"text": "\n".join(text), "segments": segments, "options": options,
            "question": node.choice.question if node.choice else "", "ended": bool(node.ending),
            "title": book.bible.title if book.bible else ""}


def generate(state, scenario, duration, seed, turn, player_input, client, save, cancel=None):
    """Resume the same upstream node on retry, including its committed partial pages.

    `save` receives plain dictionaries; no client, lock, dataclass or callback is
    retained in a Ren'Py save. Callers reject updates from obsolete request epochs.
    """
    c = load_content()
    if state is None:
        if turn:
            raise ValueError("An older story needs a new adventure to use Linux LeanWriter")
        card = card_for(scenario, seed, client)
        book = book_ops.new_book(c, card, length_for(duration), seed)
        state = {"book": book.to_dict(), "card": card, "node": "n", "turn": 0}
    else:
        state = copy.deepcopy(state)
        book = Book.from_dict(state["book"])

    def checkpoint():
        state["book"] = book.to_dict()
        save(copy.deepcopy(state))

    if turn != state["turn"]:
        if turn != state["turn"] + 1:
            raise ValueError("Story turn does not match the saved Linux chapter")
        parent = book.nodes[state["node"]]
        if parent.status != "done" or not parent.choice:
            raise ValueError("Complete the current chapter before choosing")
        opt = next((o for o in parent.choice.options
                    if player_input in (o.id, o.text, o.id + ". " + o.text)), None)
        if opt is None:
            idea = freetext.interpret_idea(c, client, book, parent, player_input)
            if idea is None:
                raise ValueError("A choice or idea is required")
            opt, _actor = freetext.add_idea(c, book, parent, idea)
        node = book_ops.new_child(c, book, parent.id, opt)
        state.update(node=node.id, turn=turn)
    node = book.nodes[state["node"]]
    checkpoint()
    writer = LeanWriter(c, client, fallback_model=client.settings.get("fallback_model"))
    try:
        if node.status != "done":
            if node.id == "n":
                writer.opening(book, state["card"], cancel=cancel)
            else:
                writer.chapter(book, node.id, cancel=cancel)
    finally:
        checkpoint()
    return display(book, node)
