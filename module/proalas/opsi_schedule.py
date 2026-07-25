# -*- coding: utf-8 -*-
"""
ProAlas 大世界调度：按每月开荒 Enable + 适应性（同步值）开关坐标类任务，
并可选后置短猫/侵蚀1、按日期开放港口商店。
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from module.campaign.os_run import OSCampaignRun
from module.logger import logger
from module.os_handler.action_point import ActionPointLimit
from module.proalas.feature_gate import gate_task_or_skip

# 坐标清理相关（适应性达标才强制开；未达标强制关）
_COORD_TASKS = (
    'OpsiAbyssal',
    'OpsiStronghold',
    'OpsiMonthBoss',
    'OpsiObscure',
    'OpsiArchive',
)
_DEFER_TASKS = (
    'OpsiMeowfficerFarming',
    'OpsiHazard1Leveling',
)


class ProalasOpsiSchedule(OSCampaignRun):
    def _set_enable(self, task: str, enabled: bool) -> None:
        cur = bool(self.config.is_task_enabled(task))
        if cur == bool(enabled):
            return
        self.config.cross_set(keys=f'{task}.Scheduler.Enable', value=bool(enabled))
        logger.info('ProalasOpsiSchedule %s.Scheduler.Enable %s -> %s', task, cur, enabled)

    def _adapt_ready(self, adaptability) -> bool:
        """三值均达到阈值（默认含等于）视为可清理坐标。"""
        try:
            arr = np.array(adaptability, dtype=int)
        except (TypeError, ValueError):
            logger.warning('ProalasOpsiSchedule adaptability parse fail: %r', adaptability)
            return False
        if arr.size < 3:
            logger.warning('ProalasOpsiSchedule adaptability incomplete: %r', adaptability)
            return False
        threshold = int(getattr(self.config, 'ProalasOpsiSchedule_AdaptThreshold', 400) or 400)
        ready = bool((arr[:3] >= threshold).all())
        logger.attr('OpsiAdaptability', f'{list(arr[:3])} threshold>={threshold} ready={ready}')
        return ready

    def _apply_coord_tasks(self, ready: bool) -> None:
        for task in _COORD_TASKS:
            self._set_enable(task, ready)

    def _apply_defer_meow_hazard1(self, ready: bool) -> None:
        """
        后置短猫和71：仅当适应性达标时生效。
        日服刷新后上半个 12 小时关掉短猫/侵蚀1，下半个 12 小时再打开，给坐标留行动力。
        未达标则完全不碰短猫/71（交给用户原开关）。
        """
        defer = bool(getattr(self.config, 'ProalasOpsiSchedule_DeferMeowAndHazard1', False))
        if not defer:
            logger.info('ProalasOpsiSchedule DeferMeowAndHazard1=off, leave meow/CL1 untouched')
            return
        if not ready:
            logger.info('ProalasOpsiSchedule adapt not ready, ignore DeferMeowAndHazard1')
            return
        hour = datetime.now().hour
        # 与 Alas ServerUpdate 习惯一致：按本机日界粗分上下半天
        enable_farm = hour >= 12
        logger.info(
            'ProalasOpsiSchedule defer window hour=%s -> meow/CL1 Enable=%s',
            hour,
            enable_farm,
        )
        for task in _DEFER_TASKS:
            self._set_enable(task, enable_farm)

    def _apply_shop_by_day(self) -> None:
        unlock_day = int(getattr(self.config, 'ProalasOpsiSchedule_ShopUnlockDay', 20) or 20)
        unlock_day = max(1, min(28, unlock_day))
        today = datetime.now().day
        enable = today > unlock_day
        logger.info(
            'ProalasOpsiSchedule shop day today=%s unlock_after=%s -> OpsiShop=%s',
            today,
            unlock_day,
            enable,
        )
        self._set_enable('OpsiShop', enable)

    def _read_adaptability(self):
        campaign = self.load_campaign()
        campaign.os_map_goto_globe(unpin=False)
        campaign.device.screenshot()
        return campaign.get_adaptability()

    def _delay_next(self, ready: bool) -> None:
        """
        默认每天一次（ServerUpdate）。
        开启后置且适应性达标时：上半天结束后预约到当日 12:00 再跑，以便重新打开短猫/71。
        """
        defer = bool(getattr(self.config, 'ProalasOpsiSchedule_DeferMeowAndHazard1', False))
        if defer and ready:
            now = datetime.now()
            if now.hour < 12:
                noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
                logger.info('ProalasOpsiSchedule defer: next run at noon %s', noon)
                self.config.task_delay(target=noon)
                return
        self.config.task_delay(server_update=True)

    def run(self):
        if gate_task_or_skip(self, 'ProalasOpsiSchedule'):
            return
        logger.hr('ProalasOpsiSchedule', level=1)

        if not self.config.is_task_enabled('OpsiExplore'):
            logger.info('OpsiExplore.Scheduler.Enable=false, skip entire OpsiSchedule')
            self.config.task_delay(server_update=True)
            return

        try:
            adaptability = self._read_adaptability()
        except ActionPointLimit:
            logger.warning('ProalasOpsiSchedule ActionPointLimit while reading adapt')
            self.config.task_delay(server_update=True)
            return
        except Exception as e:
            logger.exception('ProalasOpsiSchedule read adaptability failed: %s', e)
            self.config.task_delay(server_update=True)
            return

        ready = self._adapt_ready(adaptability)
        self._apply_coord_tasks(ready)
        self._apply_defer_meow_hazard1(ready)
        self._apply_shop_by_day()
        self._delay_next(ready)
