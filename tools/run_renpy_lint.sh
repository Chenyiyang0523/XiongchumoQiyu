#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime_root=${XCMQY_RUNTIME_ROOT:-$project_root/archive/legacy-releases/credentials-compromised-2026-08-23/XcmQy/XcmQy_v1.01}
launcher="$runtime_root/lib/py3-linux-x86_64/XiongchumoQiyu"

if [ ! -x "$launcher" ]; then
    echo "Ren'Py 运行时不可用：$launcher" >&2
    echo "可通过 XCMQY_RUNTIME_ROOT 指向同版本的解包运行时。" >&2
    exit 2
fi

temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-lint.XXXXXX")
cleanup() {
    chmod -R u+w "$temp_root" 2>/dev/null || true
    rm -rf -- "$temp_root"
}
trap cleanup EXIT INT TERM

cp -R "$project_root/game" "$temp_root/game"

docker run --rm --platform linux/amd64 \
    -e SDL_VIDEODRIVER=dummy \
    -e SDL_AUDIODRIVER=dummy \
    -v "$runtime_root:/runtime:ro" \
    -v "$temp_root/game:/runtime/game" \
    debian:bookworm-slim \
    /bin/sh -c 'exec /runtime/lib/py3-linux-x86_64/XiongchumoQiyu --lint'
