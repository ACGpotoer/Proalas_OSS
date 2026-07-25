# -*- coding: utf-8 -*-
"""ProAlas AI 自动规划：Scheduler 定时 + TimerPlan 串行触发。"""
from __future__ import annotations

from module.logger import logger
from module.proalas.ai_planner.cycle import run_ai_planner_cycle
from module.proalas.feature_gate import gate_task_or_skip
from module.ui.ui import UI


class ProalasAiPlanner(UI):
    def run(self):
        if gate_task_or_skip(self, 'ProalasAiPlanner'):
            return
        logger.hr('ProalasAiPlanner', level=1)
        run_ai_planner_cycle(self.config, trigger='scheduler')
