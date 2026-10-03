"""GLM's native JSON endpoint using the user's existing Claude Code configuration."""
from urllib.parse import urlparse
import os
from service.anthropic_provider import ClaudeSettingsProvider
from service.provider import Provider, ModelError, SYSTEM
from service.prompts import LIVE_SYSTEM


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
        self.max_tokens=int(os.environ.get('XCMQY_MODEL_MAX_TOKENS','20000'))
        self.extra_payload={'thinking':{'type':'enabled'},'reasoning_effort':self.reasoning_effort}
        self.system=LIVE_SYSTEM

    def call(self,stage,context,schema,record):
        def measured(metric):
            metric['transport']='glm-coding-native'
            metric['reasoning_effort']=self.reasoning_effort
            metric['cost_basis']='configured_token_rate_estimate' if metric['cost_usd'] is not None else 'coding_plan_charge_unknown'
            record(metric)
        return Provider.call(self,stage,context,schema,measured)

    def payload_options(self,stage):
        return {**self.extra_payload,'temperature':.9 if stage=='concepts' else .2 if stage=='review' else .55}
