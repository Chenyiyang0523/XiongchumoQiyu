#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sdk_root=${XCMQY_RENPY_SDK_ROOT:-$project_root/.local/toolchains/renpy-8.5.2-sdk}
output_root="$project_root/docs/release/1.1.0-rc.1"
temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-regression.XXXXXX")
trap 'chmod -R u+w "$temp_root"; rm -rf -- "$temp_root"' EXIT INT TERM
cp -R "$project_root/game" "$temp_root/game"
cp "$project_root/tools/qa_regression.rpy" "$temp_root/game/qa_regression.rpy"
XCMQY_QA_OUTPUT="$output_root" RENPY_DISABLE_SOUND=1 RENPY_SIMPLE_EXCEPTIONS=1 RENPY_SKIP_SPLASHSCREEN=1 \
 "$sdk_root/renpy.sh" --savedir "$temp_root/saves" "$temp_root" test regression --overwrite-screenshots --report-detailed
