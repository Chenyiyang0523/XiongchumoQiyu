#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sdk_root="$project_root/.local/toolchains/renpy-8.5.2-sdk"
: "$XCMQY_REAL_QA_ENDPOINT" "$XCMQY_REAL_QA_GUARDIAN"
output_root="$project_root/docs/v2/native-qa"
temp_root=$(mktemp -d /tmp/xcmqy-live.XXXXXX)
trap 'chmod -R u+w "$temp_root"; rm -rf -- "$temp_root"' EXIT INT TERM
mkdir -p "$output_root"
cp -R "$project_root/game" "$temp_root/game"
cp "$project_root/tools/qa_live_service.rpy" "$temp_root/game/qa_live_service.rpy"
XCMQY_QA_OUTPUT="$output_root" RENPY_DISABLE_SOUND=1 RENPY_SIMPLE_EXCEPTIONS=1 \
  "$sdk_root/renpy.sh" --savedir "$temp_root/saves" "$temp_root" test live_online --overwrite-screenshots --report-detailed
