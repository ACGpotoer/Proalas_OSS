# -*- coding: utf-8 -*-
"""
定时计划主任务：统一开关驱动活动同步 + UP 抽卡检测 + TimeTable 刷新。

子任务 Scheduler 与主任务联动（见 timer_plan_bundle）；仅本任务进入 Alas 调度队列。
"""
from __future__ import annotations

from module.logger import logger
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.timer_plan_bundle import run_timer_plan_bundle
from module.ui.ui import UI


class ProalasTimerPlan(UI):
    def run(self):
        if gate_task_or_skip(self, 'ProalasTimerPlan'):
            return
        logger.hr('ProalasTimerPlan', level=1)
        run_timer_plan_bundle(self.config, self.device)
        self.config.task_delay(server_update=True)
