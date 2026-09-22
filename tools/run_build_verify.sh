#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sdk_root=${XCMQY_RENPY_SDK_ROOT:-$project_root/.local/toolchains/renpy-8.5.2-sdk}

if [ ! -x "$sdk_root/renpy.sh" ]; then
    echo "缺少 Ren'Py 8.5.2 SDK：$sdk_root" >&2
    exit 2
fi

temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-build.XXXXXX")
cleanup() {
    chmod -R u+w "$temp_root" 2>/dev/null || true
    rm -rf -- "$temp_root"
}
trap cleanup EXIT INT TERM

cp -R "$project_root/game" "$temp_root/game"
mkdir -p "$temp_root/dist" "$temp_root/unpacked"

build_log="$temp_root/build.log"
if ! (
    cd "$sdk_root"
    ./renpy.sh launcher distribute \
        --destination "$temp_root/dist" \
        --package pc \
        --no-archive \
        --no-update \
        "$temp_root"
) >"$build_log" 2>&1; then
    echo "Ren'Py PC 构建失败，末尾日志如下：" >&2
    tail -n 80 "$build_log" >&2
    exit 1
fi

package_file=$(find "$temp_root/dist" -maxdepth 1 -type f -name '*.zip' -print -quit)
if [ -z "$package_file" ]; then
    echo "构建失败：未生成 PC ZIP。" >&2
    find "$temp_root/dist" -maxdepth 2 -print >&2
    exit 1
fi

unzip -q "$package_file" -d "$temp_root/unpacked"

script_bytecode=$(find "$temp_root/unpacked" -type f -name 'script.rpyc' -print -quit)
if [ -z "$script_bytecode" ]; then
    echo "构建失败：发行包中缺少项目 script.rpyc。" >&2
    exit 1
fi
packaged_game=$(dirname "$script_bytecode")

for forbidden_name in archive .local assets-source python-packages tts_cache saves docs packaging .qoder; do
    if find "$temp_root/unpacked" -type d -name "$forbidden_name" -print -quit | grep -q .; then
        echo "发行内容混入禁用目录：$forbidden_name" >&2
        exit 1
    fi
done

source_hit=$(find "$packaged_game" -type f -name '*.rpy' -print -quit)
if [ -n "$source_hit" ]; then
    echo "发行包的 game/ 目录混入项目源码：$source_hit" >&2
    exit 1
fi

security_hits=$(rg -a -n -l \
    'sk-[A-Za-z0-9_-]{16,}|CERT_NONE|check_hostname\s*=\s*False|api\.deepseek\.com|edge_tts|(?:[A-Za-z]:[\\/]+Users[\\/]+|/Users/[^/[:space:]]+/)' \
    "$packaged_game" || true)
if [ -n "$security_hits" ]; then
    echo "发行包的 game/ 内容命中安全扫描规则：" >&2
    printf '%s\n' "$security_hits" >&2
    exit 1
fi

file_count=$(find "$temp_root/unpacked" -type f | wc -l | tr -d ' ')
package_size=$(du -h "$package_file" | awk '{print $1}')
echo "[OK] PC 临时构建通过：${file_count} 个文件，ZIP ${package_size}；发行内容扫描无风险残留。"
