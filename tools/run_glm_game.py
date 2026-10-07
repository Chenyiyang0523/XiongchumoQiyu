#!/usr/bin/env python3
"""Run the game with a metered BigModel bridge; provider keys stay in this process."""
import argparse
from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import select
import socket
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 2 * 1024 * 1024
ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


class GLM:
    def __init__(self):
        self.key = os.environ.get("XCMQY_API_KEY", "").strip()
        config = Path.home() / ".xcmqy/config.json"
        if not self.key and config.is_file():
            self.key = str(json.loads(config.read_text(encoding="utf-8")).get("api_key", "")).strip()
        if not self.key:
            settings = Path(os.environ.get("XCMQY_CLAUDE_SETTINGS", str(Path.home() / ".claude/settings.json")))
            env = json.loads(settings.read_text(encoding="utf-8")).get("env", {})
            if urlparse(env.get("ANTHROPIC_BASE_URL", "")).hostname != "open.bigmodel.cn":
                raise ValueError("No local BigModel credential configured")
            self.key = env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY")
        self.model = re.sub(r"\[1m\]$", "", os.environ.get("XCMQY_GLM_MODEL", "glm-4.7"), flags=re.I)
        if not self.key or not self.model.startswith("glm-"):
            raise ValueError("GLM model or credential missing")
        self.slots = threading.BoundedSemaphore(3)

    @contextmanager
    def forward(self, payload):
        """Relay the Linux client's body verbatim, including role-specific models.

        Streaming is essential: LeanWriter closes the connection at the current
        chapter's choice/end line instead of generating the remaining book.
        """
        if not isinstance(payload.get("messages"), list) or not payload["messages"]:
            raise ValueError("messages required")
        if not isinstance(payload.get("model"), str) or not payload["model"].startswith("glm-"):
            raise ValueError("GLM model required")
        request = Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode(),
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.key})
        # A streamed chapter can request one repair while its outer stream is open.
        with self.slots:
            with urlopen(request, timeout=100) as response:
                yield response

    def complete(self, messages):
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "max_tokens": 8000, "temperature": 0.9, "top_p": 0.95}
        if self.model in {"glm-4.7", "glm-4.7-flashx", "glm-5-turbo"}:
            payload["thinking"] = {"type": "disabled"}
        else:
            payload.update(thinking={"type": "enabled"}, reasoning_effort="low")
        with self.forward(payload) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("GLM response too large")
        return json.loads(raw)


def handler_for(provider, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_error(401)
                return
            try:
                self.connection.settimeout(110)
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= LIMIT:
                    self.send_error(413)
                    return
                payload = json.loads(self.rfile.read(size))
                with provider.forward(payload) as response:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream" if payload.get("stream") else "application/json")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    if payload.get("stream"):
                        total = 0
                        while True:
                            # Stop upstream when LeanWriter has closed at its fork.
                            readable, _, _ = select.select([self.connection], [], [], 0)
                            if readable and not self.connection.recv(1, socket.MSG_PEEK):
                                break
                            line = response.readline()
                            if not line:
                                break
                            total += len(line)
                            if total > LIMIT:
                                raise ValueError("GLM stream too large")
                            self.wfile.write(line)
                            self.wfile.flush()
                    else:
                        body = response.read(LIMIT + 1)
                        if len(body) > LIMIT:
                            raise ValueError("GLM response too large")
                        self.wfile.write(body)
            except HTTPError as exc:
                body = exc.read(LIMIT)
                self.send_response(exc.code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Normal when LeanWriter stops after the chapter's fork.
            except Exception as exc:
                print("GLM request failed: " + type(exc).__name__, flush=True)
                try:
                    self.send_error(502, "GLM unavailable; retry the current story turn")
                except OSError:
                    pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-api", action="store_true")
    args = parser.parse_args()
    provider = GLM()
    if args.check_api:
        result = provider.complete([{"role": "user", "content": "请用一句话描写熊大和熊二在森林中发现一张地图。"}])
        print(json.dumps({"model": result.get("model", provider.model), "complete": True,
                          "characters": len(result["choices"][0]["message"]["content"])}, ensure_ascii=False))
        return 0
    candidates = [Path(os.environ["XCMQY_RENPY_SDK_ROOT"])] if os.environ.get("XCMQY_RENPY_SDK_ROOT") else [
        ROOT / ".local/toolchains/renpy-8.5.2-sdk",
        Path.home() / "Downloads/熊出没奇遇/熊出没奇遇/.local/toolchains/renpy-8.5.2-sdk"]
    sdk = next((p for p in candidates if (p / "renpy.sh").is_file()), None)
    if sdk is None:
        raise ValueError("Set XCMQY_RENPY_SDK_ROOT to your Ren'Py SDK")
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(provider, token))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = os.environ.copy()
    # Never pass inherited provider credentials to the game process.
    for name in list(env):
        if name.startswith("ANTHROPIC_") or name in {"XCMQY_API_KEY", "XCMQY_LLM_KEY", "OPENAI_API_KEY"}:
            env.pop(name)
    env.update(XCMQY_AI_ENDPOINT="http://127.0.0.1:%d/v1/chat/completions" % server.server_port,
               XCMQY_AI_KEY=token, XCMQY_AI_MODEL=provider.model,
               no_proxy="localhost,127.0.0.1,::1", NO_PROXY="localhost,127.0.0.1,::1")
    saves = ROOT / ".local/player-saves"
    saves.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / ".local/renpy-runtime"
    for child in ("tmp", "cache", "data"):
        (runtime / child).mkdir(parents=True, exist_ok=True)
    # Preserve trust for saves made by the previous launcher, without changing global files.
    old_tokens = Path.home() / "Library/RenPy/tokens"
    if old_tokens.is_dir() and not (runtime / "data/tokens").exists():
        shutil.copytree(old_tokens, runtime / "data/tokens")
    env.update(RENPY_PATH_TO_SAVES=str(runtime / "data"),
               RENPY_DISABLE_BACKUPS="I take responsibility for this.",
               PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(runtime / "tmp"),
               XDG_CACHE_HOME=str(runtime / "cache"))
    print("启动 Linux 原版文字引擎：glm-4.7；点子解析/重试模型按原版配置。", flush=True)
    print("在冒险设置中选择「云端动态故事」即可使用 GLM。", flush=True)
    try:
        return subprocess.call([str(sdk / "renpy.sh"), "--savedir", str(saves), str(ROOT)], env=env, cwd=ROOT)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as exc:
        print("启动失败：" + type(exc).__name__ + "；请检查本机 GLM 配置、网络与 Ren’Py SDK。")
        raise SystemExit(1)
