"""GLM's native JSON endpoint using the user's existing Claude Code configuration."""
from urllib.parse import urlparse
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
        self.extra_payload={'thinking':{'type':'disabled'}}
        self.system=LIVE_SYSTEM

    def call(self,stage,context,schema,record):
        def measured(metric):
            metric['transport']='glm-coding-native'
            metric['cost_basis']='configured_token_rate_estimate' if metric['cost_usd'] is not None else 'coding_plan_charge_unknown'
            record(metric)
        return Provider.call(self,stage,context,schema,measured)
