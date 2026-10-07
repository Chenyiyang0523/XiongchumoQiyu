#!/usr/bin/env python3
"""Read-only audit probes for the legacy engine; no Ren'Py UI, saves, or network.

Run from any directory: python3 docs/audit/2026-10-07/probe_legacy.py
Loads the current project's actual Python definitions, with a fake transport.
Results describe observed behavior; this is not a release acceptance suite.
"""
import ast
import io
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
blocks = runpy.run_path(str(ROOT / "tools/test_core_logic.py"))["python_blocks"]
ns = {"renpy": SimpleNamespace(log=lambda _: None, restart_interaction=lambda: None,
                              invoke_in_thread=lambda *args: None)}
for module in blocks(ROOT / "game/script.rpy"):
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
for name in ("local_adventures.rpy", "story_service.rpy"):
    for module in blocks(ROOT / "game" / name):
        exec(compile(module, name, "exec"), ns)

ns["AI_ENDPOINT"] = "http://127.0.0.1/audit-never-contacted"
ns["AI_API_KEY"] = ""
results = {}

def fake_reply(payload):
    return lambda *a, **k: io.BytesIO(json.dumps(payload, ensure_ascii=False).encode())

# A provider can end an SSE response normally while truncating its content.
partial = "熊二推开门，发现"
ns["_story_urlopen"] = fake_reply({"choices": [{"message": {"content": partial},
                                                "finish_reason": "length"}]})
results["nonstream_accepts_length_stop"] = ns["_online_request"]([], False) == partial
sse = ('data: ' + json.dumps({"choices": [{"delta": {"content": partial},
                                           "finish_reason": "length"}]}, ensure_ascii=False)
       + '\n\ndata: [DONE]\n\n').encode()
ns["_story_urlopen"] = lambda *a, **k: io.BytesIO(sse)
results["stream_accepts_length_stop"] = ns["_online_request"]([], True) == partial

g = ns["StoryGame"]()
g._configure_run("熊二", "月亮列车", 10, "小朋友独立体验", "儿童难度", "", "", "", True)
g.started = True
g.turn_count = 3
g.user_responses = ["A. 跟着月亮列车", "B. 收好飞船零件", "C. 请光头强一起爬上树"]
g.messages = [{"role": "system", "content": g.system_prompt},
              {"role": "assistant", "content": "月亮列车停在树梢，车票挂在树枝上。"},
              {"role": "user", "content": g.user_responses[-1]}]

def timeout(*args, **kwargs):
    raise TimeoutError("synthetic timeout; no socket opened")

ns["_story_urlopen"] = timeout
epoch = g._reset_stream_state()
ns["call_ai_stream"](g.messages, g, epoch)
g.finalize_stream_response()
results["fallback"] = {"actual_choice": g.user_responses[-1],
                       "rendered_opening": g._full_response.splitlines()[:4],
                       "online_enabled_after_failure": g.online_enabled,
                       "local_response_stored_as_assistant": g.messages[-1]["content"] == g._full_response}

# Each tag is clamped, but the same turn can contain several tags.
g2 = ns["StoryGame"]()
for seg in ns["parse_ai_response"]("熊二搬开了树枝。\n【属性变化：智+2】\n【属性变化：智+2】"):
    if seg[0] == "stats":
        g2.apply_stats(seg[1])
results["duplicate_stat_tags"] = {"initial": 5, "final": g2.stats["智"], "change": g2.stats["智"] - 5}

g3 = ns["StoryGame"]()
ns["_commit_story_response"](g3, "【场景：狗熊岭森林】", g3._request_epoch)
results["scene_only_accepted"] = {"segments": list(g3._segment_queue),
                                  "options": ns["extract_options"](g3._full_response),
                                  "fallback_notice": g3.ai_notice}
print(json.dumps(results, ensure_ascii=False, indent=2))
