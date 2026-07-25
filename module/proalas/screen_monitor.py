# -*- coding: utf-8 -*-
"""定时截图：保存到 ./img/{config_name}/，保留最近 N 张。"""
from __future__ import annotations

from module.logger import logger
from module.proalas.screen_paths import save_device_screenshot
from module.ui.ui import UI


class ProalasScreenMonitor(UI):
    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _keep_count(self) -> int:
        keep = getattr(self.config, 'ProalasScreenMonitor_KeepCount', 10)
        try:
            keep = int(keep)
        except (TypeError, ValueError):
            keep = 10
        return max(1, keep)

    def run(self):
        logger.hr('ProalasScreenMonitor', level=1)
        config_name = self._config_name()
        keep = self._keep_count()
        self.device.screenshot()
        filename = save_device_screenshot(self.device.image, config_name, keep=keep)
        logger.info('Screenshot saved: img/%s/%s (keep=%s)', config_name, filename, keep)
        self.config.task_delay(success=True)
