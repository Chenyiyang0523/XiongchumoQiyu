#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$task_root"
if [ ! -x "$task_root/.venv/bin/python" ]; then
  python3 -m venv "$task_root/.venv"
  "$task_root/.venv/bin/python" -m pip install -r service/requirements.txt
fi
export XCMQY_LLM_BACKEND=glm-local
export XCMQY_LLM_MODEL=${XCMQY_LLM_MODEL:-glm-5.3}
export XCMQY_DATABASE=${XCMQY_DATABASE:-$task_root/.local/glm/player.sqlite}
export XCMQY_MODEL_TIMEOUT=${XCMQY_MODEL_TIMEOUT:-240}
export XCMQY_BOOK_TOKEN_LIMIT=${XCMQY_BOOK_TOKEN_LIMIT:-700000}
export XCMQY_DEVELOPMENT_MOCK=0
if [ -z "${XCMQY_LLM_PROXY:-}" ] && [ "$(uname -s)" = "Darwin" ]; then
  task_proxy=$("$task_root/.venv/bin/python" - <<'PY'
import re,subprocess
data=subprocess.check_output(['scutil','--proxy'],text=True)
def value(key):
    match=re.search(r'^\s*'+key+r'\s*:\s*(\S+)\s*$',data,re.M)
    return match.group(1) if match else ''
host,port=value('HTTPSProxy'),value('HTTPSPort')
if value('HTTPSEnable')=='1' and re.fullmatch(r'[a-zA-Z0-9.-]+',host) and port.isdigit():
    print('http://'+host+':'+port)
PY
)
  if [ -n "$task_proxy" ]; then export XCMQY_LLM_PROXY="$task_proxy"; fi
fi
if [ -z "${XCMQY_GUARDIAN_CODE:-}" ]; then
  XCMQY_GUARDIAN_CODE=$("$task_root/.venv/bin/python" - <<'PY'
from pathlib import Path
import os,secrets
p=Path('.local/glm/guardian-code.txt');p.parent.mkdir(parents=True,exist_ok=True)
if not p.exists():
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(secrets.token_urlsafe(12)+'\n')
print(p.read_text(encoding='utf-8').strip())
PY
)
  export XCMQY_GUARDIAN_CODE
fi
printf '真实 GLM 服务：http://127.0.0.1:%s\n监护人连接码：%s\n' "${XCMQY_PORT:-8001}" "$XCMQY_GUARDIAN_CODE"
exec "$task_root/.venv/bin/python" -m uvicorn service.app:create_app --factory --host 127.0.0.1 --port "${XCMQY_PORT:-8001}"
