#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sdk_root=${XCMQY_RENPY_SDK_ROOT:-$project_root/.local/toolchains/renpy-8.5.2-sdk}
output_root="$project_root/docs/qa-screenshots"

temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-visual.XXXXXX")
cleanup() {
    chmod -R u+w "$temp_root" 2>/dev/null || true
    rm -rf -- "$temp_root"
}
trap cleanup EXIT INT TERM

mkdir -p "$output_root"
cp -R "$project_root/game" "$temp_root/game"
cp "$project_root/tools/qa_visual.rpy" "$temp_root/game/qa_visual.rpy"

if [ ! -x "$sdk_root/renpy.sh" ]; then
    echo "请通过 XCMQY_RENPY_SDK_ROOT 指定 Ren'Py 8.5.2 SDK。" >&2
    exit 2
fi
XCMQY_QA_OUTPUT="$output_root" RENPY_DISABLE_SOUND=1 RENPY_SIMPLE_EXCEPTIONS=1 \
    "$sdk_root/renpy.sh" --savedir "$temp_root/saves" "$temp_root" test visual_qa --overwrite-screenshots --report-detailed

for screenshot_name in account-select.png character-select.png game-settings.png qte-accessibility.png; do
    if [ ! -s "$output_root/$screenshot_name" ]; then
        echo "视觉 QA 失败，未生成：$screenshot_name" >&2
        exit 1
    fi
done

echo "视觉 QA 截图已写入：$output_root"
