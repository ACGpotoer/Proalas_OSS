# -*- coding: utf-8 -*-
"""活动物化任务：可选从 sync gateway 拉取日历 → 物化到本机 config。"""
from __future__ import annotations

from module.logger import logger
from module.proalas.activity_materializer import materialize_activity
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.sync_gateway_client import pull_from_sync_gateway
from module.ui.ui import UI


class ProalasActivitySync(UI):
    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _pull_sync_gateway(self) -> bool:
        if not bool(getattr(self.config, 'ProalasActivitySync_SyncGatewayEnable', True)):
            logger.info('ProalasActivitySync SyncGatewayEnable=false, skip pull')
            return True
        url = str(getattr(self.config, 'ProalasActivitySync_SyncGatewayUrl', '') or '').strip()
        token = str(getattr(self.config, 'ProalasActivitySync_SyncGatewayToken', '') or '').strip()
        pull_plan = bool(getattr(self.config, 'ProalasActivitySync_PullPlanSchedule', True))
        result = pull_from_sync_gateway(
            base_url=url,
            token=token,
            pull_plan_schedule=pull_plan,
            merge_plan_with_local=True,
        )
        if result.details:
            logger.info('ProalasActivitySync gateway pull %s', '; '.join(result.details))
        if result.errors:
            logger.error('ProalasActivitySync gateway pull errors=%s', result.errors)
        return result.ok

    def run(self):
        if gate_task_or_skip(self, 'ProalasActivitySync'):
            return
        logger.hr('ProalasActivitySync', level=1)

        if not self._pull_sync_gateway():
            logger.warning('ProalasActivitySync gateway pull failed, materialize from local cache')

        allow_manifest = bool(getattr(self.config, 'ProalasActivitySync_AllowManifestFallback', True))
        result = materialize_activity(
            self._config_name(),
            allow_manifest_fallback=allow_manifest,
        )
        if result.errors:
            logger.error('ProalasActivitySync errors=%s', result.errors)
        else:
            logger.info(
                'ProalasActivitySync applied=%s date=%s source=%s',
                result.applied,
                result.date,
                (result.blue or {}).get('source', 'calendar'),
            )
        self.config.task_delay(server_update=True)
