#!/usr/bin/env python3
"""Fast, dependency-free release gate for the active Ren'Py source tree."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "game"

EXPECTED_BACKGROUNDS = (
    "forest",
    "cabin",
    "cave",
    "riverside",
    "mountain",
    "village",
)

FORBIDDEN_RUNTIME_PATHS = (
    GAME / "cache",
    GAME / "saves",
    GAME / "tts_cache",
    GAME / "python-packages",
)

TEXT_PATTERNS = {
    "疑似硬编码服务密钥": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    "禁用 TLS 证书校验": re.compile(r"CERT_NONE|check_hostname\s*=\s*False"),
    "客户端直连旧模型服务": re.compile(r"api\.deepseek\.com", re.I),
    "已移除的网络语音依赖": re.compile(r"\b(?:edge_tts|edge-tts)\b", re.I),
    "开发机绝对路径": re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+|/Users/[^/\s]+/)", re.I),
}


def fail(issues: list[str], message: str) -> None:
    issues.append(message)


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for base in (GAME,):
        if not base.exists():
            continue
        for candidate in base.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in {".rpy", ".py"}:
                files.append(candidate)
    return files


def check_text(issues: list[str]) -> int:
    count = 0
    for source in iter_source_files():
        text = source.read_text(encoding="utf-8-sig", errors="replace")
        count += 1
        for label, pattern in TEXT_PATTERNS.items():
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                fail(issues, f"{label}: {source.relative_to(ROOT)}:{line}")
    return count


def check_assets(issues: list[str]) -> None:
    for scene in EXPECTED_BACKGROUNDS:
        asset = GAME / "images" / "bg" / f"bg_{scene}.webp"
        if not asset.is_file():
            fail(issues, f"缺少规范背景: {asset.relative_to(ROOT)}")
            continue
        header = asset.read_bytes()[:12]
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
            fail(issues, f"扩展名与真实格式不符: {asset.relative_to(ROOT)}")
        if asset.stat().st_size > 2 * 1024 * 1024:
            fail(issues, f"背景超过 2 MiB 预算: {asset.relative_to(ROOT)}")

    for required in (
        GAME / "SourceHanSansLite.ttf",
        GAME / "ZCOOLKuaiLe-Regular.ttf",
        GAME / "audio" / "music.mp3",
        GAME / "gui" / "window_icon.png",
    ):
        if not required.is_file():
            fail(issues, f"缺少运行资源: {required.relative_to(ROOT)}")


def check_tree(issues: list[str]) -> None:
    for generated in FORBIDDEN_RUNTIME_PATHS:
        if generated.exists():
            fail(issues, f"运行期目录混入源码: {generated.relative_to(ROOT)}")

    compiled = sorted(GAME.glob("*.rpyc"))
    if compiled:
        fail(issues, "源码目录包含生成的 rpyc: " + ", ".join(p.name for p in compiled[:5]))

    release_suffixes = {".apk", ".exe", ".zip"}
    for child in ROOT.iterdir():
        if child.is_file() and child.suffix.lower() in release_suffixes:
            fail(issues, f"历史发行物位于工程根目录: {child.name}")

    game_size = sum(p.stat().st_size for p in GAME.rglob("*") if p.is_file())
    if game_size > 100 * 1024 * 1024:
        fail(issues, f"game/ 超过 100 MiB 预算: {game_size / 1024 / 1024:.1f} MiB")


def check_duplicate_declarations(issues: list[str]) -> None:
    declarations: dict[tuple[str, str], list[str]] = defaultdict(list)
    pattern = re.compile(r"^(screen|label|transform)\s+([A-Za-z_][\w.]*)", re.M)
    for source in GAME.glob("*.rpy"):
        text = source.read_text(encoding="utf-8-sig", errors="replace")
        for kind, name in pattern.findall(text):
            declarations[(kind, name)].append(source.name)
    for (kind, name), files in sorted(declarations.items()):
        if len(files) > 1:
            fail(issues, f"重复 {kind} 声明 {name}: {', '.join(files)}")


def check_build_rules(issues: list[str]) -> None:
    options = (GAME / "options.rpy").read_text(encoding="utf-8-sig", errors="replace")
    required_fragments = (
        "**/archive/**",
        "**/.local/**",
        "**/assets-source/**",
        "**/python-packages/**",
        "**/tts_cache/**",
        "**/packaging/**",
        "**/docs/**",
    )
    for fragment in required_fragments:
        if fragment not in options:
            fail(issues, f"构建排除规则缺失: {fragment}")


def main() -> int:
    issues: list[str] = []
    source_count = check_text(issues)
    check_assets(issues)
    check_tree(issues)
    check_duplicate_declarations(issues)
    check_build_rules(issues)

    if issues:
        print(f"[FAIL] {len(issues)} 个发布门禁问题")
        for issue in issues:
            print(" - " + issue)
        return 1

    print(f"[OK] 工程门禁通过：扫描 {source_count} 个源码文件，6 个规范背景，未发现高风险残留。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
