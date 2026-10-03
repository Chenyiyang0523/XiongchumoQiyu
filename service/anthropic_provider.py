"""Reuse local Claude Code's GLM configuration with the Messages wire protocol."""
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse
import uuid

import httpx

from service.provider import ModelError, SYSTEM

def inline_schema(schema):
    """Some GLM Messages gateways mishandle $ref, encoding nested objects as strings."""
    definitions=schema.get('$defs',{})
    def expand(value):
        if isinstance(value,list):return [expand(v) for v in value]
        if not isinstance(value,dict):return value
        if '$ref' in value:
            name=value['$ref'].removeprefix('#/$defs/')
            if name not in definitions:raise ModelError('unsupported schema reference')
            return expand({**definitions[name],**{k:v for k,v in value.items() if k!='$ref'}})
        return {k:expand(v) for k,v in value.items() if k not in {'$defs','title','default'}}
    return expand(schema)

def decode_typed_json(value, schema):
    """Decode only JSON containers required by schema, never prose or entity identities."""
    if isinstance(value,str) and schema.get('type') in {'object','array'}:
        value=json.loads(value)
    if isinstance(value,dict):
        return {k:decode_typed_json(v,schema.get('properties',{}).get(k,{})) for k,v in value.items()}
    if isinstance(value,list):return [decode_typed_json(v,schema.get('items',{})) for v in value]
    return value


class ClaudeSettingsProvider:
    is_mock = False
    combined_setup = True

    def __init__(self):
        path = Path(os.environ.get('XCMQY_CLAUDE_SETTINGS', str(Path.home()/'.claude/settings.json')))
        try:
            settings = json.loads(path.read_text()).get('env', {})
        except (OSError, ValueError) as exc:
            raise ModelError('Claude Code model settings are unavailable') from exc
        self.endpoint = os.environ.get('XCMQY_LLM_ENDPOINT') or settings.get('ANTHROPIC_BASE_URL', '')
        self.endpoint = self.endpoint.rstrip('/')
        if not self.endpoint.endswith('/messages'):
            self.endpoint += '/messages' if self.endpoint.endswith('/v1') else '/v1/messages'
        self.model = re.sub(r'\[1m\]$', '', os.environ.get('XCMQY_LLM_MODEL') or settings.get('ANTHROPIC_MODEL', ''), flags=re.I)
        self.key = os.environ.get('XCMQY_LLM_KEY') or settings.get('ANTHROPIC_AUTH_TOKEN') or settings.get('ANTHROPIC_API_KEY', '')
        parsed = urlparse(self.endpoint)
        if not self.model or not self.key or not parsed.hostname or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost','127.0.0.1','::1'})):
            raise ModelError('Configure a secure GLM endpoint, model and token in Claude Code settings')
        self.timeout = float(os.environ.get('XCMQY_MODEL_TIMEOUT', '180'))
        self.max_tokens = int(os.environ.get('XCMQY_MODEL_MAX_TOKENS', '7000'))
        self.input_price = float(os.environ.get('XCMQY_INPUT_USD_PER_MILLION', '0'))
        self.output_price = float(os.environ.get('XCMQY_OUTPUT_USD_PER_MILLION', '0'))
        self.trace = os.environ.get('XCMQY_MODEL_TRACE_DIR', '')

    def call(self, stage, context, schema, record):
        started = time.monotonic()
        metric = {'stage':stage,'provider':self.model,'transport':'anthropic-messages','mock':False,
                  'input_tokens':0,'output_tokens':0,'cost_usd':None,'seconds':0,'success':False,
                  'usage_known':False,'cost_basis':'unknown'}
        request = {'stage':stage,'context':context}
        wire_schema=inline_schema(schema)
        data = None
        try:
            payload = {'model':self.model, 'max_tokens':self.max_tokens, 'stream':False,
                       'thinking':{'type':'disabled'}, 'system':SYSTEM,
                       'messages':[{'role':'user','content':json.dumps(request,ensure_ascii=False)}],
                       'tools':[{'name':'submit_story','description':'提交本次故事JSON；必须包含所有必填字段，且不能添加字段。','input_schema':wire_schema}],
                       'tool_choice':{'type':'tool','name':'submit_story'}}
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                with client.stream('POST', self.endpoint, json=payload, headers={
                    'x-api-key':self.key, 'Authorization':'Bearer '+self.key,
                    'anthropic-version':'2023-06-01'}) as response:
                    response.raise_for_status()
                    raw=bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>2*1024*1024:raise ModelError('response too large')
            data=json.loads(raw)
            usage=data.get('usage', {})
            metric['usage_known']=all(type(usage.get(k)) is int and usage[k]>=0 for k in ['input_tokens','output_tokens'])
            if metric['usage_known']:
                metric['input_tokens']=sum(usage.get(k,0) for k in ['input_tokens','cache_read_input_tokens','cache_creation_input_tokens'])
                metric['output_tokens']=usage['output_tokens']
                if self.input_price>0 and self.output_price>0:
                    metric['cost_usd']=(metric['input_tokens']*self.input_price+metric['output_tokens']*self.output_price)/1e6
                    metric['cost_basis']='configured_token_rate_estimate'
            if data.get('stop_reason')!='tool_use':raise ModelError('truncated or incomplete response')
            blocks=data.get('content', [])
            submitted=[b for b in blocks if b.get('type')=='tool_use']
            if len(submitted)!=1 or submitted[0].get('name')!='submit_story' or any(b.get('type') not in {'text','thinking','redacted_thinking','tool_use'} for b in blocks):raise ModelError('unexpected model content or tool call')
            result=decode_typed_json(submitted[0].get('input'),wire_schema)
            if not isinstance(result,dict):raise ModelError('response must be a JSON object')
            metric['success']=True
            return result
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            if isinstance(exc,ModelError):raise
            raise ModelError('GLM response unavailable or invalid') from exc
        finally:
            metric['seconds']=round(time.monotonic()-started,3)
            record(metric)
            if self.trace:
                path=Path(self.trace);path.mkdir(parents=True,exist_ok=True)
                safe_response={k:data[k] for k in ['usage','stop_reason','model'] if k in data} if isinstance(data,dict) else None
                if safe_response is not None:safe_response['content']=[b for b in data.get('content',[]) if b.get('type')=='tool_use']
                (path/(str(time.time_ns())+'-'+uuid.uuid4().hex[:8]+'-'+stage+'.json')).write_text(
                    json.dumps({'request':request,'response':safe_response,'metric':metric},ensure_ascii=False,indent=2))
