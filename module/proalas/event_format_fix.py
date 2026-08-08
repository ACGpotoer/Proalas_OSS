# -*- coding: utf-8 -*-
"""
活动格式检测修正：T-HT 模板下扫描 t1–t3 通关星，自动写 Event / Event2 配置。

判定：准备页第一颗星有 = 已通关；三颗星均无 = 未通关 → 写 Campaign.Name（t* / ht*）。
简单/困难由章节名区分，不写 Campaign.Mode。
"""
from __future__ import annotations

from module.base.timer import Timer
from module.campaign.run import CampaignRun
from module.exception import CampaignNameError, RequestHumanTakeover
from module.ui.assets import BACK_ARROW, DAILY_CHECK
from module.logger import logger
from module.proalas.event_tht_config import (
    MAP_ACH_PUSH,
    THT_HARD_STAGES,
    THT_NORMAL_STAGES,
    apply_tht_farm_ht3,
    apply_tht_push_pair,
)
from module.proalas.feature_gate import gate_task_or_skip


class ProalasEventFormatFix(CampaignRun):
    def _event_folder(self) -> str | None:
        found = []
        for task in ('Coalition', 'Event', 'Event2'):
            folder = self.config.cross_get(f'{task}.Campaign.Event')
            if folder and str(folder).strip() not in ('', 'campaign_main'):
                found.append(str(folder).strip())
        folder = getattr(self.config, 'Campaign_Event', None)
        if folder and str(folder).strip() not in ('', 'campaign_main'):
            found.append(str(folder).strip())
        # 共斗优先，避免 Event 仍挂着旧主线活动时进错分支
        for f in found:
            if str(f).startswith('coalition_'):
                return f
        return found[0] if found else None

    def _run_coalition_format_fix(self, event_folder: str) -> None:
        from module.coalition.coalition import Coalition
        from module.proalas.event_coalition_format_fix import CoalitionHorrorFormatFix

        # 复用当前 device；不 init_task，避免切走 EventFormatFix 绑定
        coalition = Coalition(config=self.config, device=self.device)
        CoalitionHorrorFormatFix(coalition).run(event_folder)

    def _set_all_cleared(self, value: bool) -> None:
        with self.config.multi_set():
            self.config.ProalasEventFormatFix_AllCleared = bool(value)

    def _apply_push_uncleared(self, t_stage: str) -> None:
        with self.config.multi_set():
            apply_tht_push_pair(
                self.config,
                event_stage=t_stage,
                event2_stage=THT_HARD_STAGES[0],
                map_achievement=MAP_ACH_PUSH,
            )
            self.config.ProalasEventFormatFix_AllCleared = False
        logger.info(
            'EventFormatFix push Event=%s Event2=%s MapAchievement=%s',
            t_stage,
            THT_HARD_STAGES[0],
            MAP_ACH_PUSH,
        )

    def _apply_t_line_farm_ht3(self) -> None:
        with self.config.multi_set():
            apply_tht_farm_ht3(self.config)
            self.config.ProalasEventFormatFix_AllCleared = True
        logger.info(
            'EventFormatFix T1-T3 cleared → Event & Event2 → %s MapAchievement=non_stop',
            THT_HARD_STAGES[-1],
        )

    def _probe_stage_star1(self, campaign, stage_name: str) -> bool | None:
        campaign.device.screenshot()
        campaign._get_stage_name(campaign.device.image)
        try:
            entrance = campaign.campaign_get_entrance(stage_name)
        except CampaignNameError:
            logger.error('EventFormatFix stage entrance missing: %s', stage_name)
            return None

        timeout = Timer(30, count=60).start()
        entrance_click = 0
        while not timeout.reached():
            campaign.device.screenshot()

            if campaign.appear(DAILY_CHECK, offset=(20, 20), interval=3):
                logger.info('%s -> %s', DAILY_CHECK, BACK_ARROW)
                campaign.device.click(BACK_ARROW)
                continue

            if campaign.handle_story_skip():
                continue

            if campaign.handle_map_preparation():
                campaign.map_get_info()
                star1 = bool(campaign.map_achieved_star_1)
                logger.info(
                    'EventFormatFix probe %s star1=%s star2=%s star3=%s cleared=%s',
                    stage_name,
                    campaign.map_achieved_star_1,
                    campaign.map_achieved_star_2,
                    campaign.map_achieved_star_3,
                    star1,
                )
                campaign.enter_map_cancel()
                return star1

            if campaign.appear_then_click(entrance, interval=2):
                entrance_click += 1
                if entrance_click > 10:
                    logger.error('EventFormatFix too many clicks entering %s', stage_name)
                    return None
                continue

        logger.error('EventFormatFix probe timeout: %s', stage_name)
        return None

    def _scan_tht_t_line(self, event_folder: str) -> None:
        self.config.override(Campaign_Event=event_folder)
        self.load_campaign('t1', folder=event_folder)
        campaign = self.campaign

        self.device.stuck_record_clear()
        self.device.click_record_clear()
        campaign.ui_goto_main()
        campaign.ensure_campaign_ui(name='t1', mode='normal')

        for stage in THT_NORMAL_STAGES:
            star1 = self._probe_stage_star1(campaign, stage)
            if star1 is None:
                raise RequestHumanTakeover
            if not star1:
                self._apply_push_uncleared(stage)
                return

        self._apply_t_line_farm_ht3()

    def run(self):
        if gate_task_or_skip(self, 'ProalasEventFormatFix'):
            return
        logger.hr('ProalasEventFormatFix', level=1)

        if not bool(getattr(self.config, 'ProalasEventFormatFix_EnableFix', True)):
            logger.info('EventFormatFix disabled by EnableFix=false')
            self.config.task_delay(server_update=True)
            return

        # 计划表无活动时禁止开荒写回（避免把共斗/Event 又打开）
        try:
            from datetime import datetime

            from module.proalas.event_campaign_orchestrator import is_event_day_blue
            from module.proalas.plan_quadrant_view import get_blue_payload

            device_id = str(getattr(self.config, 'config_name', '') or 'alas')
            blue = get_blue_payload(device_id, datetime.now().strftime('%Y-%m-%d'))
            if not is_event_day_blue(blue):
                logger.info(
                    'EventFormatFix skip — not_event_day mode=%s fmt=%s',
                    (blue or {}).get('mode') if isinstance(blue, dict) else None,
                    (blue or {}).get('event_format') if isinstance(blue, dict) else None,
                )
                with self.config.multi_set():
                    self.config.cross_set('ProalasEventFormatFix.Scheduler.Enable', False)
                    self.config.cross_set('Event.Scheduler.Enable', False)
                    self.config.cross_set('Event2.Scheduler.Enable', False)
                    self.config.cross_set('Coalition.Scheduler.Enable', False)
                self.config.task_delay(server_update=True)
                return
        except Exception as e:
            logger.warning('EventFormatFix event-day guard failed: %s', e)

        event_folder = self._event_folder()
        if not event_folder or str(event_folder).strip() == 'campaign_main':
            logger.info('EventFormatFix no active event folder — disable and skip')
            with self.config.multi_set():
                self.config.cross_set('ProalasEventFormatFix.Scheduler.Enable', False)
            self.config.task_delay(server_update=True)
            return

        from module.proalas.event_coalition_format_fix import is_coalition_event

        if is_coalition_event(event_folder):
            logger.info('EventFormatFix coalition branch event=%s', event_folder)
            self._run_coalition_format_fix(event_folder)
            return

        template = str(getattr(self.config, 'ProalasEventFormatFix_Template', 'T-HT') or 'T-HT')
        if template != 'T-HT':
            logger.warning('EventFormatFix template %r not implemented yet, skip', template)
            self.config.task_delay(server_update=True)
            return

        logger.info('EventFormatFix template=%s event=%s', template, event_folder)
        self._scan_tht_t_line(event_folder)

        if bool(getattr(self.config, 'ProalasEventFormatFix_AutoHardFleet', True)):
            from module.proalas.event_tht_config import THT_HARD_STAGES
            from module.proalas.hard_fleet_setup import run_proactive_hard_fleet_setup

            ht_stage = str(self.config.cross_get('Event2.Campaign.Name', '') or THT_HARD_STAGES[0])
            if not ht_stage.startswith('ht'):
                ht_stage = THT_HARD_STAGES[0]
            if run_proactive_hard_fleet_setup(self, event_folder, stage=ht_stage):
                logger.info('EventFormatFix proactive hard fleet setup done (%s)', ht_stage)

        self.config.task_delay(server_update=True)
