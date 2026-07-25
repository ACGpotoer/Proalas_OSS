# -*- coding: utf-8 -*-
"""
智能换队 — 编队概览页死坐标流程（1280×720）。

加速策略：
  - 缩短点击间隔；去掉 1s 硬等待
  - 每队仅第 1 槽完整 reset+「未满级」；2–6 槽沿用筛选状态不再开面板
  - 多支练级队同会话：只进一次编队，队间只切舰队不回主界面
"""
from __future__ import annotations

import time

import cv2

from typing import Any, Dict, List, Tuple

from module.base.utils import crop, load_image
from module.logger import logger
from module.proalas import fleet_swap_assets as A
from module.proalas.dock_filter_map import get_slot
from module.ui.ui import UI

FilterKey = Tuple[str, str]

FILTER_RESET_KEYS: List[FilterKey] = [
    ('index', 'all'),
    ('rarity', 'all'),
    ('extra', 'no_limit'),
    ('faction', 'all'),
]

# reset 后只需点「未满级」（其余已在 reset 里设好）
FILTER_LEVEL_APPLY: List[FilterKey] = [
    ('extra', 'not_level_max'),
]

FILTER_PRESETS: Dict[str, Dict[str, List[FilterKey]]] = {
    'level': {
        'reset': list(FILTER_RESET_KEYS),
        'apply': list(FILTER_LEVEL_APPLY),
    },
}

IMPLEMENTED_TYPES = frozenset({'level'})


def _level_apply_keys(faction_pref: str = 'all') -> List[FilterKey]:
    keys: List[FilterKey] = list(FILTER_LEVEL_APPLY)
    if faction_pref and faction_pref != 'all':
        keys.append(('faction', faction_pref))
    return keys


def swap_level_teams(
    ui: UI,
    team_nos: List[int],
    *,
    team_type: str = 'level',
    faction_pref: str = 'all',
) -> Dict[int, Dict[str, Any]]:
    """连续换多支练级队（共享一次进编队导航）。"""
    results: Dict[int, Dict[str, Any]] = {}
    if not team_nos:
        return results

    preset = FILTER_PRESETS.get(team_type)
    if not preset or team_type not in IMPLEMENTED_TYPES:
        for team_no in team_nos:
            results[team_no] = {
                'team': team_no,
                'type': team_type,
                'skipped': True,
                'error': 'type_not_implemented',
                'slotsAttempted': 0,
                'slotsOk': 0,
                'slotsFailed': 0,
            }
        return results

    apply_keys = _level_apply_keys(faction_pref)
    runner = _FleetSwapRunner(ui)
    if not runner.goto_formation_overview():
        err = 'nav_formation_failed'
        for team_no in team_nos:
            results[team_no] = _empty_stats(team_no, team_type, error=err)
        runner.return_main()
        return results

    for team_no in team_nos:
        stats = _empty_stats(team_no, team_type)
        if not runner.select_fleet(team_no):
            stats['error'] = 'select_fleet_failed'
            results[team_no] = stats
            continue

        runner._filter_primed = False
        for slot in range(1, 7):
            stats['slotsAttempted'] += 1
            ok = runner.swap_one_slot(
                slot,
                reset_keys=preset['reset'],
                apply_keys=apply_keys,
            )
            if ok:
                stats['slotsOk'] += 1
            else:
                stats['slotsFailed'] += 1

        if stats['slotsOk'] == 0 and stats['slotsFailed'] > 0:
            stats['error'] = 'all_slots_failed'
        logger.info(
            'FleetSwap: team=%s ok=%s fail=%s',
            team_no,
            stats['slotsOk'],
            stats['slotsFailed'],
        )
        results[team_no] = stats

    runner.return_main()
    return results


def swap_team_ships(ui: UI, team_no: int, *, team_type: str = 'level') -> Dict[str, Any]:
    """单队换船（兼容旧调用）。"""
    batch = swap_level_teams(ui, [team_no], team_type=team_type)
    return batch.get(team_no) or _empty_stats(team_no, team_type, error='swap_failed')


def _empty_stats(team_no: int, team_type: str, *, error: str = '') -> Dict[str, Any]:
    return {
        'team': team_no,
        'type': team_type,
        'slotsAttempted': 0,
        'slotsOk': 0,
        'slotsFailed': 0,
        'skipped': False,
        'error': error,
    }


class _FleetSwapRunner:
    def __init__(self, ui: UI) -> None:
        self.ui = ui
        self._filter_primed = False

    def _tap(self, xy: tuple[int, int], *, delay: float | None = None) -> None:
        wait = A._AFTER_TAP if delay is None else delay
        self.ui.device.click_adb(*xy)
        self.ui.device.sleep(max(float(wait), 0.2))

    def _screenshot(self) -> None:
        self.ui.device.screenshot()

    def _appear(self, button, *, tag: str = '') -> bool:
        self._screenshot()
        matched = self.ui.appear(button, offset=(15, 15), similarity=A._TEMPLATE_SIMILARITY)
        logger.info('FleetSwap %s match=%s', tag or button.name, matched)
        return matched

    def _match_area_template(
        self,
        file: str,
        area: tuple[int, int, int, int],
        *,
        similarity: float,
        tag: str,
    ) -> bool:
        """全屏素材 + area 裁切，与当前 device.image 同区域逐像素比对。"""
        self._screenshot()
        template = load_image(file, area)
        search = crop(self.ui.device.image, area, copy=False)
        if template.shape != search.shape:
            logger.warning(
                'FleetSwap %s size mismatch tpl=%s search=%s',
                tag,
                template.shape,
                search.shape,
            )
            return False
        res = cv2.matchTemplate(template, search, cv2.TM_CCOEFF_NORMED)
        sim = float(res[0, 0]) if res.size == 1 else float(res.max())
        matched = sim > similarity
        logger.info(
            'FleetSwap %s sim=%.4f match=%s need>%.2f',
            tag,
            sim,
            matched,
            similarity,
        )
        return matched

    def _on_six_slot_view(self) -> bool:
        return self._match_area_template(
            A.SIX_SLOT_OVERVIEW_FILE,
            A.SIX_SLOT_OVERVIEW_AREA,
            similarity=A._SIX_SLOT_SIMILARITY,
            tag='SixSlotOverview',
        )

    def ensure_six_slot_view(self, *, max_attempts: int = 2) -> bool:
        """六船位概览：模板命中=已在该页；否则点「编队界面」区域中心进入。"""
        for attempt in range(1, max_attempts + 1):
            if self._on_six_slot_view():
                return True
            logger.info(
                'FleetSwap 不在六船位 attempt=%s click=%s',
                attempt,
                A.SIX_SLOT_OVERVIEW_CENTER,
            )
            self.ui.device.click_adb(*A.SIX_SLOT_OVERVIEW_CENTER)
            self.ui.device.sleep(A._AFTER_SLOT)
        return self._on_six_slot_view()

    def return_main(self) -> None:
        self.ui.ui_goto_main()

    def goto_formation_overview(self) -> bool:
        self.ui.ui_goto_main()
        logger.info('FleetSwap 进编队 %s', A.CLICK_FORMATION)
        self._tap(A.CLICK_FORMATION, delay=A._AFTER_NAV)
        return True

    def select_fleet(self, team_no: int) -> bool:
        if not 1 <= team_no <= len(A.FLEET_CLICKS):
            logger.error('FleetSwap invalid team_no=%s', team_no)
            return False
        fleet_xy = A.FLEET_CLICKS[team_no - 1]
        logger.info('FleetSwap 打开舰队菜单 %s', A.CLICK_OPEN_FLEET_MENU)
        self._tap(A.CLICK_OPEN_FLEET_MENU)
        logger.info('FleetSwap 选择第 %s 舰队 %s', team_no, fleet_xy)
        self._tap(fleet_xy, delay=A._AFTER_SLOT)
        if not self.ensure_six_slot_view():
            logger.error('FleetSwap 切队后未能进入六船位 team=%s', team_no)
            return False
        return True

    def _click_filter_keys(self, keys: List[FilterKey]) -> None:
        prev: tuple[int, int] | None = None
        for section, key in keys:
            slot = get_slot(section, key)
            xy = tuple(slot['click'])
            if prev == xy:
                self.ui.device.sleep(0.15)
            logger.info(
                'FleetSwap filter %s.%s (%s) %s',
                section,
                key,
                slot.get('label_zh', ''),
                xy,
            )
            self._tap(xy, delay=A._AFTER_FILTER_CLICK)
            prev = xy

    def _open_filter_panel(self) -> bool:
        for attempt in range(1, A._MAX_FILTER_OPEN_RETRY + 1):
            logger.info('FleetSwap 打开筛选 attempt=%s', attempt)
            self._tap(A.CLICK_OPEN_FILTER, delay=A._AFTER_FILTER_OPEN)
            self._screenshot()
            if self.ui.appear(
                A.FILTER_CONFIRM,
                offset=A.FILTER_CONFIRM_OFFSET,
                similarity=A._TEMPLATE_SIMILARITY,
            ):
                logger.info('FleetSwap FilterConfirm match=True')
                return True
            logger.info('FleetSwap FilterConfirm match=False')
        return False

    def _confirm_filter_panel(self) -> None:
        if self.ui.appear_then_click(
            A.FILTER_CONFIRM,
            offset=A.FILTER_CONFIRM_OFFSET,
            interval=A._CONFIRM_INTERVAL,
        ):
            self.ui.device.sleep(A._AFTER_FILTER_DONE)
            return
        self._tap(A.CLICK_FILTER_CONFIRM_FALLBACK, delay=A._AFTER_FILTER_DONE)

    def _apply_filters_full(
        self,
        reset_keys: List[FilterKey],
        apply_keys: List[FilterKey],
    ) -> bool:
        if not self._open_filter_panel():
            return False
        self._click_filter_keys(reset_keys)
        self._click_filter_keys(apply_keys)
        self._confirm_filter_panel()
        self._filter_primed = True
        return True

    def _finish_dock_pick(self) -> None:
        """
        选船后流程：先点 1020,675，再分支：
          - 有确认弹窗 → 点确认中心 → 回六船位
          - 无弹窗 → 已直接回六船位
        """
        logger.info('FleetSwap 回六船位 %s', A.CLICK_RETURN_SLOTS)
        self._tap(A.CLICK_RETURN_SLOTS, delay=A._AFTER_SLOT)

        deadline = time.time() + A._ABOARD_CONFIRM_POLL
        while time.time() < deadline:
            self.ui.device.sleep(A._ABOARD_CONFIRM_POLL_STEP)
            if self._match_area_template(
                A.SHIP_ABOARD_CONFIRM_FILE,
                A.SHIP_ABOARD_CONFIRM_AREA,
                similarity=A._ABOARD_CONFIRM_SIMILARITY,
                tag='ShipAboardConfirm',
            ):
                logger.info(
                    'FleetSwap 点确认弹窗 %s',
                    A.SHIP_ABOARD_CONFIRM_CENTER,
                )
                self.ui.device.click_adb(*A.SHIP_ABOARD_CONFIRM_CENTER)
                self.ui.device.sleep(A._AFTER_CONFIRM)
                return
        logger.info('FleetSwap 无确认弹窗，直接回六船位')

    def swap_one_slot(
        self,
        slot: int,
        *,
        reset_keys: List[FilterKey],
        apply_keys: List[FilterKey],
    ) -> bool:
        if not 1 <= slot <= len(A.SHIP_SLOT_CLICKS):
            return False
        click = A.SHIP_SLOT_CLICKS[slot - 1]
        logger.info('FleetSwap slot=%s 船位 %s', slot, click)
        self._tap(click, delay=A._AFTER_SLOT)

        if not self._filter_primed:
            if not self._apply_filters_full(reset_keys, apply_keys):
                logger.warning('FleetSwap slot=%s 筛选失败', slot)
                self.ensure_six_slot_view()
                return False
        else:
            logger.info('FleetSwap slot=%s 沿用筛选，跳过面板', slot)

        logger.info('FleetSwap slot=%s 选船 %s', slot, A.CLICK_PICK_SHIP)
        self._tap(A.CLICK_PICK_SHIP, delay=A._AFTER_PICK)
        self._finish_dock_pick()
        if not self._on_six_slot_view():
            self.ensure_six_slot_view()
        return True
