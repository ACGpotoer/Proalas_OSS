# -*- coding: utf-8 -*-
"""计划表任务：刷新日历视图 + 可选触发活动物化。"""
from __future__ import annotations

from datetime import datetime

from module.logger import logger
from module.proalas.activity_materializer import materialize_activity
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.plan_schedule_api import export_plan_api_spec, get_plan_month_view
from module.ui.ui import UI


class ProalasPlanCalendar(UI):
    def run(self):
        if gate_task_or_skip(self, 'ProalasPlanCalendar'):
            return
        logger.hr('ProalasPlanCalendar', level=1)
        device_id = str(getattr(self.config, 'config_name', '') or 'alas')
        ai_on = bool(getattr(self.config, 'ProalasPlanCalendar_EnableAi', False))
        sync_on = bool(getattr(self.config, 'ProalasPlanCalendar_SyncActivityOnRun', True))
        today = datetime.now()
        view = get_plan_month_view(device_id, today.year, today.month)
        entries = sum(len(w.get('entries') or []) for week in view.get('weeks') or [] for w in week if w.get('inMonth'))
        logger.info(
            'ProalasPlanCalendar device=%s enableAi=%s syncActivity=%s monthEntries=%s api=%s',
            device_id,
            ai_on,
            sync_on,
            entries,
            export_plan_api_spec()['module'],
        )
        if sync_on:
            result = materialize_activity(device_id)
            logger.info(
                'ProalasPlanCalendar activity sync applied=%s date=%s',
                result.applied,
                result.date,
            )
        self.config.task_delay(server_update=True)
