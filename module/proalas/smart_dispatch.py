# -*- coding: utf-8 -*-
"""智能资源调度（WebUI 配置；调度逻辑待后续实现）。"""
from __future__ import annotations

from module.logger import logger
from module.proalas.feature_gate import gate_task_or_skip
from module.ui.ui import UI


def effective_resource_preference(config) -> str:
    """返回 rmb | money；PreferMoney 优先于 PreferRmb。"""
    prefer_money = bool(getattr(config, 'ProalasSmartDispatch_PreferMoney', False))
    if prefer_money:
        return 'money'
    prefer_rmb = bool(getattr(config, 'ProalasSmartDispatch_PreferRmb', True))
    return 'rmb' if prefer_rmb else 'money'


class ProalasSmartDispatch(UI):
    def run(self):
        if gate_task_or_skip(self, 'ProalasSmartDispatch'):
            return
        logger.hr('ProalasSmartDispatch', level=1)
        enabled = bool(getattr(self.config, 'ProalasSmartDispatch_EnableSmartDispatch', False))
        pref = effective_resource_preference(self.config)
        logger.info(
            'ProalasSmartDispatch enabled=%s preference=%s (edit in WebUI)',
            enabled,
            pref,
        )
        self.config.task_delay(server_update=True)
