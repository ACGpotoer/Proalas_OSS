# -*- coding: utf-8 -*-
"""账户管理（套餐信息在 WebUI 编辑；本任务无自动化操作）。"""
from __future__ import annotations

from module.logger import logger
from module.ui.ui import UI

_PLAN_LABEL = {
    'normal': 'Normal',
    'pro': 'Pro',
    'pro_plus': 'Pro+',
}


class ProalasAccount(UI):
    def run(self):
        logger.hr('ProalasAccount', level=1)
        plan = getattr(self.config, 'ProalasAccount_PlanType', '') or 'normal'
        expire = getattr(self.config, 'ProalasAccount_ExpireAt', '') or ''
        logger.info(
            'ProalasAccount plan=%s expire=%s (edit in WebUI)',
            _PLAN_LABEL.get(plan, plan),
            expire,
        )
        self.config.task_delay(server_update=True)
