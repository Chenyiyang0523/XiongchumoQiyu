import json
import subprocess

import pytest

from service.claude_cli import ClaudeCLIProvider
from service.provider import ModelError, create_provider


def configured(monkeypatch, tmp_path, response, returncode=0):
    settings = tmp_path/'settings.json'
    settings.write_text(json.dumps({'env':{'ANTHROPIC_MODEL':'glm-test',
        'ANTHROPIC_BASE_URL':'https://model.example/api/anthropic', 'ANTHROPIC_AUTH_TOKEN':'test-private-token'},
        'hooks':{'SessionStart':['must-never-run']}}))
    monkeypatch.setenv('XCMQY_CLAUDE_SETTINGS', str(settings))
    monkeypatch.setenv('XCMQY_LLM_BACKEND', 'claude-cli')
    monkeypatch.delenv('XCMQY_LLM_MODEL', raising=False)
    monkeypatch.setattr('service.claude_cli.shutil.which', lambda _: '/test/claude')
    calls = []
    class Process:
        pid = 999999
        def __init__(self, command, **kwargs):
            self.returncode = returncode
            calls.append((command, kwargs))
        def communicate(self, input=None, timeout=None):
            return json.dumps(response), ''
    monkeypatch.setattr('service.claude_cli.subprocess.Popen', Process)
    return create_provider(), calls


def successful(**overrides):
    return dict({'subtype':'success','is_error':False,'stop_reason':'end_turn','num_turns':1,
        'result':'{"approved":true,"issues":[]}',
        'usage':{'input_tokens':20,'output_tokens':10,'cache_read_input_tokens':30,
                 'cache_creation_input_tokens':4,'server_tool_use':{}},
        'total_cost_usd':0.12,'modelUsage':{'glm-test':{'costBasis':'unknown'}}}, **overrides)


def test_local_credentials_stay_out_of_arguments_and_hooks(monkeypatch, tmp_path):
    provider, calls = configured(monkeypatch,tmp_path,successful())
    metrics=[]
    assert provider.call('review',{}, {},metrics.append)['approved'] is True
    command, kwargs = calls[0]
    assert 'test-private-token' not in str(command)
    assert kwargs['env']['ANTHROPIC_AUTH_TOKEN']=='test-private-token'
    assert command[command.index('--tools')+1]==''
    assert command[command.index('--setting-sources')+1]==''
    assert '--no-session-persistence' in command and '--strict-mcp-config' in command
    assert metrics[0]['input_tokens']==54
    assert metrics[0]['cost_usd'] is None and metrics[0]['reported_cost_usd']==0.12
    assert metrics[0]['cost_basis']=='unknown'


@pytest.mark.parametrize('overrides', [
    {'stop_reason':'max_tokens'}, {'subtype':'error_max_turns'}, {'is_error':True},
    {'num_turns':2}, {'result':'{"cut":'}, {'result':'[]'},
    {'subagent_stats':{'spawned':1}},
    {'usage':{'input_tokens':20,'output_tokens':10,'server_tool_use':{'web_search_requests':1}}},
])
def test_partial_and_extra_model_work_never_commit(monkeypatch,tmp_path,overrides):
    provider,_=configured(monkeypatch,tmp_path,successful(**overrides));metrics=[]
    with pytest.raises(ModelError):provider.call('proposal',{}, {},metrics.append)
    assert len(metrics)==1 and not metrics[0]['success']


def test_rate_estimate_is_explicitly_separate_from_cli_report(monkeypatch,tmp_path):
    monkeypatch.setenv('XCMQY_INPUT_USD_PER_MILLION','2')
    monkeypatch.setenv('XCMQY_OUTPUT_USD_PER_MILLION','8')
    provider,_=configured(monkeypatch,tmp_path,successful());metrics=[]
    provider.call('review',{}, {},metrics.append)
    assert metrics[0]['cost_usd']==pytest.approx((54*2+10*8)/1e6)
    assert metrics[0]['reported_cost_usd']==0.12
    assert metrics[0]['cost_basis']=='configured_token_rate_estimate'


def test_timeout_terminates_model_process_group(monkeypatch,tmp_path):
    provider,_=configured(monkeypatch,tmp_path,successful());metrics=[];signals=[]
    class TimeoutProcess:
        pid=999999
        def __init__(self,*args,**kwargs):self.attempts=0
        def communicate(self,input=None,timeout=None):
            self.attempts+=1
            if self.attempts==1:raise subprocess.TimeoutExpired('claude',timeout)
            return '', ''
    monkeypatch.setattr('service.claude_cli.subprocess.Popen',TimeoutProcess)
    monkeypatch.setattr('service.claude_cli.os.killpg',lambda pid,sig:signals.append((pid,sig)))
    with pytest.raises(ModelError,match='timed out'):provider.call('review',{}, {},metrics.append)
    assert len(signals)==1 and not metrics[0]['success']
