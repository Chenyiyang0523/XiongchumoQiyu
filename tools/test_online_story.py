#!/usr/bin/env python3
"""Ren'Py/Linux integration regressions; all model responses are scripted, no API use."""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_core_logic import python_blocks

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))
import linux_story as bridge
from xcmengine import book_ops, freetext, prompts
from xcmengine.config import Settings
from xcmengine.lean import LeanWriter
from xcmengine.llm import ChatClient, FakeTransport
from xcmengine.models import Book

FIXTURE = json.loads((ROOT / "tools/fixtures/linux_writer.json").read_text())
HEAD, CHAPTERS = FIXTURE["head"], FIXTURE["chapters"]


def load_story():
    ns = {"renpy": SimpleNamespace(
        log=lambda _: None, restart_interaction=lambda: None,
        invoke_in_thread=lambda fn, *args: fn(*args),
        file=lambda name: (ROOT / "game" / name).open("rb"))}
    for module in python_blocks(ROOT / "game/script.rpy"):
        selected = []
        for node in module.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
                selected.append(node)
            elif isinstance(node, ast.ClassDef) and node.name == "StoryGame":
                selected.append(node)
            elif isinstance(node, ast.Assign):
                try:
                    ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    continue
                selected.append(node)
        exec(compile(ast.Module(body=selected, type_ignores=[]), "script.rpy", "exec"), ns)
    for name in ("local_adventures.rpy", "story_service.rpy", "story_writing.rpy"):
        for module in python_blocks(ROOT / "game" / name):
            exec(compile(module, name, "exec"), ns)
    ns["AI_ENDPOINT"] = "http://127.0.0.1/v1/chat/completions"
    ns["AI_API_KEY"] = "test-only"
    return ns


def sse(*objects, finish="stop"):
    text = "\n".join(json.dumps(x, ensure_ascii=False) for x in objects) + "\n"
    chunks = [{"choices": [{"delta": {"content": text[i:i+7]}}]} for i in range(0, len(text), 7)]
    chunks += [{"choices": [{"delta": {}, "finish_reason": finish}]}]
    return "\n\n".join("data: " + json.dumps(c, ensure_ascii=False) for c in chunks) + "\n\ndata: [DONE]\n\n"


def client(script):
    fake = FakeTransport(script)
    cl = ChatClient(Settings({"retries": 0}, env={}), transport=fake, api_key="test-only", sleep=lambda _: None)
    return cl, fake


def script_for(chapters=CHAPTERS):
    return [("ok", sse(*([HEAD] if i == 0 else []), *[x for chapter in chapters[i:] for x in chapter]))
            for i in range(len(chapters))]


class LinuxStoryTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_story()
        self.g = self.ns["StoryGame"]()
        self.cl, self.fake = client(script_for())
        self.ns["linux_story_client"] = lambda: self.cl
        self.scenario = bridge.load_content().card("c34")["hook"]

    def begin(self):
        self.g.start_stream("熊二", self.scenario, 10, online_enabled=True)
        self.assertFalse(self.g.ai_error, self.g.ai_error)
        self.g.finalize_stream_response()

    def choose(self, index=0):
        oid, label = self.ns["story_options"](self.g)[index]
        self.g.continue_story_stream(oid + ". " + label)
        self.assertFalse(self.g.ai_error, self.g.ai_error)
        self.g.finalize_stream_response()

    def test_vendored_files_are_byte_identical_to_linux(self):
        manifest = json.loads((ROOT / "game/xcmengine/UPSTREAM.json").read_text())
        self.assertEqual(manifest["source_commit"], "85140750c5e2d2ee5760af158dd9ffd1b9b000e8")
        for path, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)

    def test_entire_book_requests_and_state_equal_direct_linux_calls(self):
        self.begin()
        c = bridge.load_content()
        direct, transport = client(script_for())
        card = copy.deepcopy(self.g._linux_state["card"])
        book = book_ops.new_book(c, card, "medium", self.g.run_id)
        writer = LeanWriter(c, direct)
        writer.opening(book, card)
        node = book.nodes["n"]
        self.assertEqual(self.g._linux_state["book"], book.to_dict())
        for pick in (0, 1, 2):
            opt = node.choice.options[pick]
            node = book_ops.new_child(c, book, node.id, opt)
            writer.chapter(book, node.id)
            self.choose(pick)
            self.assertEqual(self.g._linux_state["book"], book.to_dict())
        bodies = [json.loads(r["body"]) for r in self.fake.requests]
        self.assertEqual(bodies, [json.loads(r["body"]) for r in transport.requests])
        self.assertEqual(len(bodies), 4)  # every whole-book reply was cut at its current fork
        self.assertEqual([len(n["pages"]) for n in self.g._linux_state["book"]["nodes"].values()], [3, 3, 2, 4])
        self.assertTrue(self.g.ended)
        self.assertEqual(bodies[0]["model"], "glm-4.7")
        self.assertEqual(bodies[0]["thinking"], {"type": "disabled"})
        self.assertEqual(bodies[0]["temperature"], 0.9)
        self.assertEqual(self.g.stats, {"智": 5, "勇": 5, "体": 5, "友": 5})

    def test_partial_failure_retry_keeps_pages_choice_and_save_state(self):
        self.begin()
        prefix = sse(CHAPTERS[1][0])
        # A complete first page, then a fatal account error on continuation.
        self.cl, _ = client([("ok", prefix), ("http", 401, "{}")])
        self.g.continue_story_stream("B. " + self.ns["story_options"](self.g)[1][1])
        self.assertTrue(self.g.ai_error)
        snapshot = pickle.loads(pickle.dumps(self.g.__getstate__()))
        state = copy.deepcopy(self.g._linux_state)
        self.assertEqual(state["node"], "n.B")
        self.assertEqual(len(state["book"]["nodes"]["n.B"]["pages"]), 1)
        self.assertFalse(self.g._segment_queue)
        restored = self.ns["StoryGame"]()
        before_count = len(snapshot["messages"])
        restored.__setstate__(snapshot)
        self.cl, fake = client([("ok", sse(*CHAPTERS[1][1:]))])
        restored.retry_story_stream()
        self.assertFalse(restored.ai_error)
        restored.finalize_stream_response()
        restored.finalize_stream_response()
        self.assertEqual(restored.turn_count, 1)
        self.assertEqual(restored.user_responses, snapshot["user_responses"])
        self.assertEqual(len(restored.messages), before_count + 1)
        self.assertEqual(len(restored._linux_state["book"]["nodes"]["n.B"]["pages"]), 3)
        self.assertIn("接着写第五页", json.loads(fake.requests[0]["body"])["messages"][-1]["content"])

    def test_free_idea_uses_original_interpreter_and_choice_object(self):
        self.begin()
        idea_reply = {"category": "action", "actor": "xionger", "action": "用蜂蜜罐当灯笼", "object": "蜂蜜灯笼", "hint": "罐子亮了起来"}
        self.cl, fake = client([("ok", sse(idea_reply)), ("ok", sse(*CHAPTERS[1]))])
        self.g.continue_story_stream("用蜂蜜罐当灯笼")
        self.assertFalse(self.g.ai_error)
        book = Book.from_dict(self.g._linux_state["book"])
        self.assertEqual(self.g._linux_state["node"], "n.P1")
        self.assertEqual(book.nodes["n"].choice.option("P1").label, "用蜂蜜罐当灯笼")
        self.assertEqual(json.loads(fake.requests[0]["body"])["model"], "glm-4.7-flashx")
        self.assertIn("小读者自己想到了", json.loads(fake.requests[1]["body"])["messages"][-1]["content"])

    def test_display_keeps_all_lines_and_guest_names_without_legacy_parser(self):
        self.begin()
        book = Book.from_dict(self.g._linux_state["book"])
        node = book.nodes["n"]
        view = bridge.display(book, node)
        texts = [s[2] if s[0] == "dialogue" else s[1] for s in view["segments"] if s[0] != "scene"]
        self.assertEqual(texts, [l.text for p in node.pages for l in p.lines])
        self.assertTrue(any(s[0] == "dialogue" and s[1] == "小云朵" for s in view["segments"]))
        self.assertEqual(view["question"], node.choice.question)
        self.ns["parse_ai_response"] = lambda _: self.fail("Linux pages must not use legacy text parsing")
        self.choose()

    def test_stale_epoch_and_old_save_never_replace_the_story(self):
        self.begin()
        state = copy.deepcopy(self.g._linux_state)
        self.assertFalse(self.ns["_commit_story_response"](self.g, "unwanted", self.g._request_epoch - 1))
        self.assertEqual(state, self.g._linux_state)
        del self.g._story_writer
        self.g.continue_story_stream("A")
        self.assertIn("旧版文字引擎", self.g.ai_error)
        self.assertFalse(self.g._segment_queue)
        self.assertEqual(state, self.g._linux_state)

    def test_short_book_uses_linux_two_choices_and_four_page_finale(self):
        self.cl, fake = client(script_for([CHAPTERS[0], CHAPTERS[2], CHAPTERS[3]]))
        self.g.start_stream("熊二", self.scenario, 5, online_enabled=True)
        self.g.finalize_stream_response()
        self.choose()
        self.choose()
        self.assertTrue(self.g.ended)
        self.assertEqual(self.g.turn_count, 2)
        self.assertEqual(len(fake.requests), 3)

    def test_custom_scenario_uses_linux_premise_interpreter(self):
        premise = {"title": "月亮列车", "hook": "熊二发现一列停在树梢的月亮列车", "cast": ["xionger", "xiongda"], "tone": "好笑"}
        self.cl, fake = client([("ok", sse(premise)), *script_for()])
        self.g.start_stream("熊二", "想看熊二坐月亮列车", 10, online_enabled=True)
        self.assertFalse(self.g.ai_error)
        self.assertTrue(self.g._linux_state["card"]["custom"])
        request = json.loads(fake.requests[0]["body"])
        self.assertEqual(request["messages"], prompts.premise_messages(bridge.load_content(), "想看熊二坐月亮列车"))


class TransportTests(unittest.TestCase):
    def test_only_complete_stop_is_accepted_for_nonstory_requests(self):
        ns = load_story()
        for reason in ("length", "content_filter", None, "stop"):
            for stream in (False, True):
                choice = {"finish_reason": reason, "delta" if stream else "message": {"content": "回顾"}}
                raw = json.dumps({"choices": [choice]}, ensure_ascii=False)
                raw = ("data: " + raw + "\n\ndata: [DONE]\n\n") if stream else raw
                ns["_story_urlopen"] = lambda *a, **k: io.BytesIO(raw.encode())
                if reason == "stop":
                    self.assertEqual(ns["_online_request"]([], stream), "回顾")
                else:
                    with self.assertRaises(ValueError):
                        ns["_online_request"]([], stream)


if __name__ == "__main__":
    unittest.main(verbosity=2)
