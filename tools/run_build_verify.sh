#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sdk_root=${XCMQY_RENPY_SDK_ROOT:-$project_root/.local/toolchains/renpy-8.5.2-sdk}
output_root=${XCMQY_RELEASE_OUTPUT:-$project_root/dist/1.1.0-rc.1}
python3 "$project_root/tools/check_project.py"
temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-build.XXXXXX")
trap 'chmod -R u+w "$temp_root"; rm -rf -- "$temp_root"' EXIT INT TERM
cp -R "$project_root/game" "$temp_root/game"
mkdir -p "$temp_root/dist" "$output_root"
(cd "$sdk_root" && ./renpy.sh launcher distribute --destination "$temp_root/dist" --package pc --package mac --no-update "$temp_root") >"$output_root/build.log" 2>&1
python3 "$project_root/tools/verify_release.py" "$temp_root"/dist/*.zip >"$output_root/verification.json"
cp "$temp_root"/dist/*.zip "$output_root/"
cat "$output_root/verification.json"
echo "[OK] 已验证真正归档的 Mac/PC 安装包：$output_root"
