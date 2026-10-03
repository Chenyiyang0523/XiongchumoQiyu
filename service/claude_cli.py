"""One isolated, tool-free GLM call through the user's local Claude Code CLI."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

from service.provider import ModelError, SYSTEM


class ClaudeCLIProvider:
    is_mock = False

    def __init__(self):
        self.binary = shutil.which(os.environ.get('XCMQY_CLAUDE_BINARY', 'claude'))
        if not self.binary:
            raise ModelError('Claude Code CLI is not installed on this service host')
        path = Path(os.environ.get('XCMQY_CLAUDE_SETTINGS', str(Path.home()/'.claude/settings.json')))
        try:
            settings = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ModelError('Claude Code settings are unavailable') from exc
        self.env = os.environ.copy()
        # Inherit only the provider configuration; never execute user/project hooks or plugins.
        for key, value in settings.get('env', {}).items():
            if key.startswith('ANTHROPIC_') or key in {'API_TIMEOUT_MS', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}:
                self.env[key] = str(value)
        self.model = os.environ.get('XCMQY_LLM_MODEL', '').strip() or self.env.get('ANTHROPIC_MODEL', '').strip()
        if not self.model or not self.env.get('ANTHROPIC_BASE_URL') or not (self.env.get('ANTHROPIC_AUTH_TOKEN') or self.env.get('ANTHROPIC_API_KEY')):
            raise ModelError('Configure the GLM model, endpoint and token in local Claude Code settings')
        self.env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
        self.env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] = os.environ.get('XCMQY_MODEL_MAX_TOKENS', '7000')
        self.timeout = float(os.environ.get('XCMQY_MODEL_TIMEOUT', '180'))
        self.input_price = float(os.environ.get('XCMQY_INPUT_USD_PER_MILLION', '0'))
        self.output_price = float(os.environ.get('XCMQY_OUTPUT_USD_PER_MILLION', '0'))
        self.trace = os.environ.get('XCMQY_MODEL_TRACE_DIR', '')

    def call(self, stage, context, schema, record):
        started = time.monotonic()
        metric = {'stage':stage, 'provider':self.model, 'transport':'claude-cli', 'mock':False,
                  'input_tokens':0, 'output_tokens':0, 'usage_known':False, 'cost_usd':None,
                  'reported_cost_usd':None, 'cost_basis':'unknown', 'seconds':0, 'success':False}
        data = None
        request = {'stage':stage, 'context':context, 'schema':schema}
        command = [self.binary, '-p', '--output-format', 'json', '--tools', '',
                   '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                   '--setting-sources', '', '--disable-slash-commands', '--no-session-persistence',
                   '--no-chrome', '--model', self.model, '--system-prompt', SYSTEM]
        try:
            with tempfile.TemporaryDirectory(prefix='xcmqy-model-') as cwd:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding='utf-8', env=self.env, cwd=cwd, start_new_session=True)
                try:
                    stdout, _ = process.communicate(json.dumps(request, ensure_ascii=False), timeout=self.timeout)
                except subprocess.TimeoutExpired as exc:
                    if os.name=='nt':process.terminate()
                    else:os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        if os.name=='nt':process.kill()
                        else:os.killpg(process.pid, signal.SIGKILL)
                        process.communicate()
                    raise ModelError('Claude Code model call timed out; confirmed state preserved') from exc
            if len(stdout.encode()) > 2*1024*1024:
                raise ModelError('model response too large')
            data = json.loads(stdout)
            usage = data.get('usage', {})
            metric['usage_known'] = all(type(usage.get(k)) is int and usage[k] >= 0 for k in ['input_tokens','output_tokens'])
            if metric['usage_known']:
                metric['input_tokens'] = sum(usage.get(k, 0) for k in ['input_tokens','cache_read_input_tokens','cache_creation_input_tokens'])
                metric['output_tokens'] = usage['output_tokens']
            metric['reported_cost_usd'] = data.get('total_cost_usd')
            bases = {v.get('costBasis', 'unknown') for v in data.get('modelUsage', {}).values()}
            if metric['usage_known'] and self.input_price > 0 and self.output_price > 0:
                metric['cost_usd'] = (metric['input_tokens']*self.input_price + metric['output_tokens']*self.output_price)/1e6
                metric['cost_basis'] = 'configured_token_rate_estimate'
            elif bases and bases <= {'known', 'provider'} and type(metric['reported_cost_usd']) in {int,float}:
                metric['cost_usd'] = metric['reported_cost_usd']
                metric['cost_basis'] = 'provider_reported'
            # A CLI success message is insufficient: require one complete, tool-free model turn.
            if process.returncode or data.get('is_error') or data.get('subtype') != 'success' or data.get('stop_reason') != 'end_turn':
                raise ModelError('Claude Code model response incomplete or unavailable')
            if data.get('num_turns') != 1 or data.get('subagent_stats', {}).get('spawned', 0) or any(usage.get('server_tool_use', {}).values()):
                raise ModelError('model call exceeded the single-turn, tool-free contract')
            result = json.loads(data.get('result', ''))
            if not isinstance(result, dict):
                raise ModelError('response must be a JSON object')
            metric['success'] = True
            return result
        except (OSError, ValueError, TypeError) as exc:
            if isinstance(exc, ModelError):
                raise
            raise ModelError('Claude Code model response unavailable or invalid') from exc
        finally:
            metric['seconds'] = round(time.monotonic()-started, 3)
            record(metric)
            if self.trace:
                path = Path(self.trace)
                path.mkdir(parents=True, exist_ok=True)
                safe_response = {k:data[k] for k in ['result','usage','stop_reason','subtype','is_error','num_turns'] if k in data} if isinstance(data, dict) else None
                (path/(str(time.time_ns())+'-'+uuid.uuid4().hex[:8]+'-'+stage+'.json')).write_text(
                    json.dumps({'request':request,'response':safe_response,'metric':metric}, ensure_ascii=False, indent=2), encoding='utf-8')
