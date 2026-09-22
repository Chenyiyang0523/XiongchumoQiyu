#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime_root=${XCMQY_RUNTIME_ROOT:-$project_root/archive/legacy-releases/credentials-compromised-2026-08-23/XcmQy/XcmQy_v1.01}
launcher="$runtime_root/lib/py3-linux-x86_64/XiongchumoQiyu"
sdk_root=${XCMQY_RENPY_SDK_ROOT:-$project_root/.local/toolchains/renpy-8.5.2-sdk}
output_root="$project_root/docs/qa-screenshots"
qa_image="xcmqy-renpy-qa:bookworm"

temp_root=$(mktemp -d "${TMPDIR:-/tmp}/xcmqy-visual.XXXXXX")
cleanup() {
    chmod -R u+w "$temp_root" 2>/dev/null || true
    rm -rf -- "$temp_root"
}
trap cleanup EXIT INT TERM

mkdir -p "$output_root"
cp -R "$project_root/game" "$temp_root/game"
cp "$project_root/tools/qa_visual.rpy" "$temp_root/game/qa_visual.rpy"

if [ "$(uname -s)" = "Darwin" ]; then
    if [ ! -x "$sdk_root/renpy.sh" ]; then
        echo "缺少原生 Ren'Py 8.5.2 SDK：$sdk_root" >&2
        echo "请从官方发布页下载并通过 XCMQY_RENPY_SDK_ROOT 指定。" >&2
        exit 2
    fi
    XCMQY_QA_OUTPUT="$output_root" \
    RENPY_DISABLE_SOUND=1 \
    RENPY_SIMPLE_EXCEPTIONS=1 \
        "$sdk_root/renpy.sh" --savedir "$temp_root/saves" "$temp_root" test visual_qa --overwrite-screenshots --report-detailed
else
    if [ ! -x "$launcher" ]; then
        echo "Ren'Py 运行时不可用：$launcher" >&2
        exit 2
    fi
    if ! docker image inspect "$qa_image" >/dev/null 2>&1; then
        docker build --platform linux/amd64 \
            -f "$project_root/tools/Dockerfile.renpy-qa" \
            -t "$qa_image" \
            "$project_root/tools"
    fi
    docker run --rm --platform linux/amd64 \
        -e SDL_VIDEODRIVER=x11 \
        -e SDL_AUDIODRIVER=dummy \
        -e LIBGL_ALWAYS_SOFTWARE=1 \
        -e RENPY_SKIP_SPLASHSCREEN=1 \
        -e RENPY_SKIP_MAIN_MENU=1 \
        -e RENPY_SIMPLE_EXCEPTIONS=1 \
        -e XCMQY_QA_OUTPUT=/qa-output \
        -v "$runtime_root:/runtime:ro" \
        -v "$temp_root/game:/runtime/game" \
        -v "$output_root:/qa-output" \
        "$qa_image" \
        /bin/sh -c 'xvfb-run -a -s "-screen 0 1920x1080x24" timeout -k 3s 45s /runtime/lib/py3-linux-x86_64/XiongchumoQiyu /runtime test visual_qa --overwrite-screenshots --report-detailed'
fi

for screenshot_name in account-select.png character-select.png game-settings.png qte-accessibility.png; do
    if [ ! -s "$output_root/$screenshot_name" ]; then
        echo "视觉 QA 失败，未生成：$screenshot_name" >&2
        exit 1
    fi
done

echo "视觉 QA 截图已写入：$output_root"
