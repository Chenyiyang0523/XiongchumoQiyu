#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sdk_root=${XCMQY_RENPY_SDK_ROOT:-$project_root/.local/toolchains/renpy-8.5.2-sdk}
output_root="$project_root/docs/v2/native-qa"
temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-book.XXXXXX")
trap 'chmod -R u+w "$temp_root"; rm -rf -- "$temp_root"' EXIT INT TERM
mkdir -p "$output_root"
cp -R "$project_root/game" "$temp_root/game"
cp "$project_root/tools/qa_book_v2.rpy" "$temp_root/game/qa_book_v2.rpy"
XCMQY_QA_OUTPUT="$output_root" RENPY_DISABLE_SOUND=1 RENPY_SIMPLE_EXCEPTIONS=1 \
  "$sdk_root/renpy.sh" --savedir "$temp_root/saves" "$temp_root" test picturebook --overwrite-screenshots --report-detailed
"$project_root/.venv/bin/python" "$project_root/tools/prepare_local_fixture.py" "$temp_root/local-operations.json"
XCMQY_LOCAL_OPS_BOOK="$temp_root/local-operations.json" XCMQY_QA_OUTPUT="$output_root" RENPY_DISABLE_SOUND=1 RENPY_SIMPLE_EXCEPTIONS=1 \
  "$sdk_root/renpy.sh" --savedir "$temp_root/saves" "$temp_root" test local_operations --overwrite-screenshots --report-detailed
