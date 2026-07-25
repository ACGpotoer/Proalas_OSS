# -*- coding: utf-8 -*-
"""
ProAlas 资源采集（Alas 原生 Device / UI / OCR）。

数据路径：
  - 油/物资/Rmb → Alas 历史日志（OCR_OIL / OCR_COIN / SHOP_GEMS）
  - 活动 PT / 建造魔方 → 任务内 OCR
  - 船坞占用 current/total → 主动进船坞 OCR（ReadBoatDock）
  - 收藏率 BoatRate → ReadBoatRate（内部 ProalasBoatMessage，须在船坞之后）

TimerPlan bundle 在 AI 规划前串行调用；独立 Scheduler 仍可用于手动兜底。
"""
from __future__ import annotations

from typing import Any

from module.campaign.campaign_status import CampaignStatus
from module.config.deep import deep_get
from module.gacha.gacha_reward import OCR_BUILD_CUBE_COUNT
from module.gacha.ui import GachaUI
from module.logger import logger
from module.proalas.boat_rate import ProalasBoatMessage
from module.proalas_collector.log_sync import read_oil_coin_rmb_from_logs
from module.proalas_collector.userdata import write_collector_snapshot
from module.retire.assets import DOCK_CHECK
from module.retire.enhancement import OCR_DOCK_AMOUNT
from module.ui.page import page_dock


class ProalasCollector(CampaignStatus, GachaUI):
    """只读采集，不提交建造/不跑战役。"""

    def _read_oil_coin_rmb_from_log(self) -> dict[str, Any]:
        device_id = str(getattr(self.config, 'config_name', '') or 'alas')
        log_dir = getattr(self.config, 'ProalasCollector_AlasLogPath', '') or ''
        log_dir = str(log_dir).strip() or None
        return read_oil_coin_rmb_from_logs(device_id, log_dir)

    def _read_event_pt(self) -> dict[str, Any]:
        self.ui_goto_event()
        self.device.screenshot()
        pt = int(self.get_event_pt() or 0)
        logger.info('ProalasCollector Event_PT=%s', pt)
        self.ui_goto_main()
        return {'act_pt': pt}

    def _read_build_cube(self) -> dict[str, Any]:
        self.ui_goto_gacha()
        if not self.gacha_load_ensure():
            logger.warning('ProalasCollector: gacha page not ready, skip cube')
            self.ui_goto_main()
            return {}
        cube = int(OCR_BUILD_CUBE_COUNT.ocr(self.device.image) or 0)
        logger.attr('BUILD_CUBE_COUNT', cube)
        logger.info('ProalasCollector cube=%s', cube)
        self.ui_goto_main()
        return {'cube': cube}

    def _read_boat_dock(self) -> dict[str, Any]:
        """主动进船坞 OCR 占用与上限（不依赖退役任务日志）。"""
        self.ui_goto_main()
        self.ui_goto(page_dock)
        self.device.screenshot()
        if not self.appear(DOCK_CHECK, offset=(20, 20)):
            logger.warning('ProalasCollector: dock page not ready, skip boat_dock')
            self.ui_goto_main()
            return {}
        try:
            current, _, total = OCR_DOCK_AMOUNT.ocr(self.device.image)
        except Exception as e:
            logger.warning('ProalasCollector: dock OCR failed: %s', e)
            self.ui_goto_main()
            return {}
        if total <= 0:
            logger.warning('ProalasCollector: dock OCR total=%s invalid', total)
            self.ui_goto_main()
            return {}
        dock_str = f'{int(current)}/{int(total)}'
        logger.attr('BOAT_DOCK', dock_str)
        logger.attr('BOAT_MAX', int(total))
        logger.info('ProalasCollector boat_dock=%s boat_max=%s', dock_str, total)
        self.ui_goto_main()
        return {'boat_dock': dock_str, 'boat_max': int(total)}

    def _read_boat_rate(self, *, boat_max_hint: int | None = None) -> dict[str, Any]:
        helper = ProalasBoatMessage(config=self.config, device=self.device)
        rate, ok = helper.collect_boat_rate(boat_max_hint=boat_max_hint)
        if ok:
            return {'boat_rate': rate}
        return {}

    def run(self, *, skip_task_delay: bool = False):
        logger.hr('ProalasCollector', level=1)
        cfg = self.config

        self.ui_goto_main()

        snapshot: dict[str, Any] = {}
        boat_max_hint: int | None = None

        if getattr(cfg, 'ProalasCollector_ReadOilCoin', True):
            snapshot.update(self._read_oil_coin_rmb_from_log())

        skip_pt = bool(deep_get(self.config.data, ['ProalasData', 'SkipEventPt'], False))
        if skip_pt:
            logger.info('ProalasCollector SkipEventPt=True, skip Event_PT reading')
        elif getattr(cfg, 'ProalasCollector_ReadEventPt', True):
            # 非活动日没有活动入口：硬进 page_event 会卡在战役菜单狂点
            from module.proalas.event_campaign_orchestrator import is_event_day_blue
            from module.proalas.plan_quadrant_view import get_blue_payload
            from datetime import datetime

            device_id = str(getattr(cfg, 'config_name', '') or 'alas')
            today = datetime.now().strftime('%Y-%m-%d')
            blue = get_blue_payload(device_id, today)
            if not is_event_day_blue(blue):
                logger.info(
                    'ProalasCollector skip Event_PT — not_event_day mode=%s',
                    (blue or {}).get('mode') if isinstance(blue, dict) else None,
                )
            else:
                snapshot.update(self._read_event_pt())

        if getattr(cfg, 'ProalasCollector_ReadBuildCube', True):
            snapshot.update(self._read_build_cube())
        else:
            self.ui_goto_main()

        if getattr(cfg, 'ProalasCollector_ReadBoatDock', True):
            dock_patch = self._read_boat_dock()
            snapshot.update(dock_patch)
            try:
                boat_max_hint = int(dock_patch.get('boat_max') or 0) or None
            except (TypeError, ValueError):
                boat_max_hint = None

        if getattr(cfg, 'ProalasCollector_ReadBoatRate', True):
            snapshot.update(self._read_boat_rate(boat_max_hint=boat_max_hint))

        device_id = str(getattr(cfg, 'config_name', '') or 'alas')
        if getattr(cfg, 'ProalasCollector_WriteUserData', True) and snapshot:
            ok = write_collector_snapshot(device_id, snapshot, config=self.config)
            if ok:
                logger.info(
                    'ProalasCollector ProalasData updated config=%s keys=%s',
                    device_id,
                    sorted(snapshot.keys()),
                )
            else:
                logger.warning('ProalasCollector ProalasData write failed config=%s', device_id)
        elif not snapshot:
            logger.warning('ProalasCollector: empty snapshot, nothing written')

        if not skip_task_delay:
            self.config.task_delay(server_update=True)
