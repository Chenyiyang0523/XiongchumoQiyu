#!/usr/bin/env python3
"""Dependency-free regression tests for pure Python embedded in Ren'Py files."""

from __future__ import annotations

import ast
import re
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def python_blocks(source: Path) -> list[ast.Module]:
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    modules: list[ast.Module] = []
    index = 0
    while index < len(lines):
        if re.match(r"^init(?:\s+-?\d+)?\s+python:\s*$", lines[index]):
            index += 1
            body: list[str] = []
            while index < len(lines):
                line = lines[index]
                # Ren'Py 的 Python 块可包含内容顶格的三引号字符串，所以不能用
                # “无缩进”判断块结束；只在明确的 Ren'Py 顶层语句处停止。
                if re.match(r"^(?:default|screen|transform|label|style|image|define)\s+", line):
                    break
                body.append(line[4:] if line.startswith("    ") else line)
                index += 1
            modules.append(ast.parse("\n".join(body)))
        else:
            index += 1
    return modules


def load_functions(source: Path, names: tuple[str, ...], namespace: dict) -> None:
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for module in python_blocks(source):
        for node in module.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                found[node.name] = node
    missing = set(names) - set(found)
    assert not missing, f"missing functions in {source.name}: {sorted(missing)}"
    for name in names:
        module = ast.fix_missing_locations(ast.Module(body=[found[name]], type_ignores=[]))
        exec(compile(module, str(source), "exec"), namespace)


def test_story_parser() -> None:
    scene_map = {
        "forest": {"name": "狗熊岭森林"},
        "cabin": {"name": "光头强家"},
        "cave": {"name": "熊大熊二的树洞"},
        "riverside": {"name": "狗熊岭河边"},
        "mountain": {"name": "狗熊岭山顶"},
        "village": {"name": "狗熊岭村庄"},
    }
    keywords = {
        "森林": "forest", "狗熊岭": "forest", "光头强家": "cabin", "小木屋": "cabin",
        "树洞": "cave", "河边": "riverside", "山顶": "mountain", "村庄": "village",
    }
    ns = {
        "re": re,
        "SCENE_MAP": scene_map,
        "SCENE_KEYWORDS": keywords,
        "EMOTION_KEYWORDS": {"开心": ["哈哈", "太好了"]},
        "CHARACTERS": {"熊大": {}},
        "renpy": SimpleNamespace(log=lambda _message: None),
    }
    load_functions(
        ROOT / "game" / "script.rpy",
        ("infer_emotion", "normalize_scene_id", "detect_scene", "extract_options", "parse_ai_response", "extract_score_from_eval"),
        ns,
    )

    assert ns["normalize_scene_id"]("bg_riverside_2.webp") == "riverside"
    assert ns["normalize_scene_id"]("狗熊岭山顶") == "mountain"
    assert ns["normalize_scene_id"]("???", "cave") == "cave"
    assert ns["detect_scene"]("【场景：狗熊岭河边】", "forest") == "riverside"

    options = ns["extract_options"]("A. 观察线索\nB、马上行动\nC．一起商量\nD. 不应出现\nA. 重复")
    assert [item[0] for item in options] == ["A", "B", "C"]

    parsed = ns["parse_ai_response"](
        "【场景：狗熊岭山顶】\n**熊大**：\"太好了！\"\n【属性变化：智+9，友-8】\n【QTE：抓住绳子|点击|99】"
    )
    assert ("scene", "狗熊岭山顶") in parsed
    assert ("dialogue", "熊大", "太好了！", "开心") in parsed
    assert ("stats", {"智": 2, "友": -2}) in parsed
    assert ("qte", "抓住绳子", "点击", 10) in parsed
    assert len(ns["parse_ai_response"]("\n".join("一行" for _ in range(60)))) == 32
    assert ns["extract_score_from_eval"]("综合评分：999/100分") == 100
    assert ns["extract_score_from_eval"]("无分数") == 0


def test_local_story_engine() -> None:
    ns = {"_story_re": re}
    load_functions(
        ROOT / "game" / "story_service.rpy",
        (
            "sanitize_player_text", "_supporting_character", "_local_choice_effect",
            "build_local_story", "_local_score", "build_local_evaluation", "build_local_parent_report",
        ),
        ns,
    )
    assert ns["sanitize_player_text"]("  你\x00 好  ", 10) == "你 好"
    assert len(ns["sanitize_player_text"]("长" * 200, 120)) == 120

    game = SimpleNamespace(
        turn_count=0, max_turns=3, user_responses=[], character="熊大",
        scenario="寻找发光松果", ending_type="温馨成长",
        stats={"智": 5, "勇": 5, "体": 5, "友": 5},
    )
    opening = ns["build_local_story"](game)
    assert "**请选择：**" in opening and "A." in opening and "C." in opening

    game.turn_count = 1
    game.user_responses = ["B"]
    middle = ns["build_local_story"](game)
    assert "【属性变化：" in middle and "**请选择：**" in middle

    game.turn_count = 3
    ending = ns["build_local_story"](game)
    assert "【剧终】" in ending and "**请选择：**" not in ending
    assert 60 <= ns["_local_score"](game) <= 100
    assert "综合评分：" in ns["build_local_evaluation"](game)
    report = ns["build_local_parent_report"](game)
    assert "不是能力或心理测评" in report and "不应用于诊断" in report


def test_account_repair() -> None:
    persistent = SimpleNamespace(
        accounts={}, account_order=[], current_user=None, next_slot_index=0,
    )
    ns = {"persistent": persistent, "_account_time": time}
    load_functions(
        ROOT / "game" / "account_system.rpy",
        (
            "_make_empty_account_data", "_safe_list", "_safe_dict", "_safe_int",
            "repair_account_data", "repair_all_accounts", "get_user_page_range",
            "get_account_quick_page", "get_account_quick_slot", "_allocate_slot_index",
        ),
        ns,
    )
    persistent.accounts = {
        "a": {"name": "很长很长很长的名字", "slot_index": 0, "play_stats": {"highest_score": 999}, "committed_runs": list(range(250))},
        "b": {"name": "B", "slot_index": 0, "play_stats": "broken"},
    }
    persistent.account_order = ["missing", "a"]
    ns["repair_all_accounts"]()
    assert persistent.accounts["a"]["name"] == "很长很长很长"
    assert persistent.accounts["a"]["play_stats"]["highest_score"] == 100
    assert len(persistent.accounts["a"]["committed_runs"]) == 200
    assert persistent.accounts["a"]["slot_index"] != persistent.accounts["b"]["slot_index"]
    assert persistent.account_order == ["a", "b"]
    assert ns["get_user_page_range"]("a") == (1, 4)
    assert ns["get_account_quick_page"]("a") == "4"
    assert ns["get_account_quick_slot"]() == 12


def main() -> None:
    tests = (test_story_parser, test_local_story_engine, test_account_repair)
    for test in tests:
        test()
        print(f"[OK] {test.__name__}")
    print(f"[OK] {len(tests)} 组核心逻辑回归通过")


if __name__ == "__main__":
    main()
