#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sdk_root=${XCMQY_RENPY_SDK_ROOT:-$project_root/.local/toolchains/renpy-8.5.2-sdk}
if [ ! -x "$sdk_root/renpy.sh" ]; then
    echo "请通过 XCMQY_RENPY_SDK_ROOT 指定 Ren'Py 8.5.2 SDK。" >&2
    exit 2
fi
temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-lint.XXXXXX")
trap 'chmod -R u+w "$temp_root"; rm -rf -- "$temp_root"' EXIT INT TERM
cp -R "$project_root/game" "$temp_root/game"
RENPY_DISABLE_SOUND=1 "$sdk_root/renpy.sh" --savedir "$temp_root/saves" "$temp_root" lint >"$temp_root/lint.txt" 2>&1
cat "$temp_root/lint.txt"
# Ren'Py lint 遇到缺资源仍可能返回 0，必须检查诊断正文。
if rg -q '^game/.*:[0-9]+|not loadable|Could not|Exception|Error|is not defined|unknown' "$temp_root/lint.txt"; then
    echo '[FAIL] Ren\x27Py lint 有诊断，不能发布。' >&2
    exit 1
fi
