# -*- coding: utf-8 -*-
"""资源统计任务（WebUI 主用；调度可选刷新日志同步）。"""
from __future__ import annotations

from module.logger import logger
from module.proalas.resource_history import build_resource_series, current_snapshot_from_userdata
from module.ui.ui import UI


class ProalasResourceStats(UI):
    """打开 Alas WebUI 查看折线图；若被调度触发则仅写日志摘要。"""

    def run(self):
        logger.hr('ProalasResourceStats', level=1)
        device_id = str(getattr(self.config, 'config_name', '') or 'alas')
        log_dir = getattr(self.config, 'ProalasResourceStats_AlasLogPath', '') or None
        series = build_resource_series(device_id, log_dir)
        snap = current_snapshot_from_userdata(device_id)
        logger.info(
            'ProalasResourceStats device=%s log_points=%s snapshot_oil=%s',
            device_id,
            {k: len(v) for k, v in series.items() if v},
            snap.get('oil'),
        )
        self.config.task_delay(server_update=True)
