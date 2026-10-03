"""GLM's native JSON endpoint using the user's existing Claude Code configuration."""
from urllib.parse import urlparse
import os
from service.anthropic_provider import ClaudeSettingsProvider
from service.provider import Provider, ModelError, RetryableModelError, SYSTEM
from service.prompts import LIVE_SYSTEM
from service.request_slots import request_slot


class LocalGLMProvider(ClaudeSettingsProvider):
    intention_protocol=True
    combined_setup=True

    def __init__(self):
        super().__init__()
        parsed=urlparse(self.endpoint)
        if parsed.hostname!='open.bigmodel.cn':
            raise ModelError('glm-local requires a verified BigModel Claude Code endpoint')
        self.endpoint='https://open.bigmodel.cn/api/coding/paas/v4/chat/completions'
        self.reasoning_effort=os.environ.get('XCMQY_GLM_REASONING_EFFORT','low')
        if self.reasoning_effort not in {'low','high','max'}:
            raise ModelError('GLM reasoning effort must be low, high or max')
        self.repair_effort=os.environ.get('XCMQY_GLM_REPAIR_EFFORT','high')
        if self.repair_effort not in {'low','high','max'}:
            raise ModelError('GLM repair effort must be low, high or max')
        self.max_tokens=int(os.environ.get('XCMQY_MODEL_MAX_TOKENS','20000'))
        self.extra_payload={'thinking':{'type':'enabled'},'reasoning_effort':self.reasoning_effort}
        self.system=LIVE_SYSTEM
        self.concurrency=int(os.environ.get('XCMQY_GLM_CONCURRENCY','2'))
        if not 1<=self.concurrency<=4:raise ModelError('GLM concurrency must be between 1 and 4')

    def call(self,stage,context,schema,record):
        def measured(metric):
            metric['transport']='glm-coding-native'
            metric['reasoning_effort']=self.payload_options(stage)['reasoning_effort']
            metric['cost_basis']='configured_token_rate_estimate' if metric['cost_usd'] is not None else 'coding_plan_charge_unknown'
            record(metric)
        try:
            with request_slot(self.endpoint,self.concurrency,max(600,self.timeout),os.environ.get('XCMQY_GLM_LOCK_DIR')) as waiting:
                def queued_metric(metric):
                    metric['admission_wait_seconds']=waiting
                    measured(metric)
                return Provider.call(self,stage,context,schema,queued_metric)
        except TimeoutError as exc:
            record({'stage':stage,'provider':self.model,'mock':False,'input_tokens':0,'output_tokens':0,
                'cost_usd':0,'seconds':0,'success':False,'usage_known':True,'request_sent':False,
                'cost_basis':'no_request_sent','transport':'glm-coding-native'})
            raise RetryableModelError('local GLM queue busy; retry the preserved action later') from exc

    def payload_options(self,stage):
        return {**self.extra_payload,'reasoning_effort':self.repair_effort if stage in {'repair','setup_repair'} else self.reasoning_effort,
                'temperature':.9 if stage=='concepts' else .2 if stage=='review' else .55}
