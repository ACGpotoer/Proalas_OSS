# -*- coding: utf-8 -*-
"""
ProAlas 自动突破。

主界面 → 船坞 → 筛选（全部 / 除 META·全阵营外各阵营 / 品质 / 可突破）
→ 选船 → TupoInto/Yes 进突破页 → 三击确认 → 回船坞，重复 N 艘。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import List, Tuple

from module.AutoBreak import assets as A
from module.GachaUp import assets as GA
from module.logger import logger
from module.proalas import fleet_swap_assets as FSA
from module.proalas.auto_break_config import (
    FACTION_BREAK_KEYS,
    RARITY_ALL_APPLY_KEYS,
    parse_run_interval_days,
    parse_ship_rarity,
    parse_ships_per_run,
    rarity_label_zh,
)
from module.proalas.dock_filter_map import get_slot
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.tupo_tab_match import pick_tupo_into_slot, pick_tupo_into_yes_slot
from module.proalas_collector.userdata import write_auto_break_result
from module.ui.ui import UI

FilterKey = Tuple[str, str]

_FILTER_RESET: List[FilterKey] = [
    ('index', 'all'),
    ('faction', 'all'),
    ('rarity', 'all'),
    ('extra', 'no_limit'),
]


def _build_break_filter_apply(rarity_key: str) -> List[FilterKey]:
    keys: List[FilterKey] = [('index', 'all')]
    for faction_key in FACTION_BREAK_KEYS:
        keys.append(('faction', faction_key))
    if rarity_key == 'all':
        for rk in RARITY_ALL_APPLY_KEYS:
            keys.append(('rarity', rk))
    elif rarity_key:
        keys.append(('rarity', rarity_key))
    keys.append(('extra', 'can_limit_break'))
    return keys


class ProalasAutoBreak(UI):
    breakthrough_count: int = 0
    has_breakthrough: bool = False
    skipped_empty: bool = False

    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _tap(
        self,
        xy: tuple[int, int],
        *,
        delay: float = A._AFTER_CLICK,
        prev: tuple[int, int] | None = None,
    ) -> None:
        if prev is not None and prev == xy:
            logger.info('AutoBreak 连续同坐标 %s，额外等待 %ss', xy, A._SAME_POS_EXTRA_DELAY)
            self.device.sleep(A._SAME_POS_EXTRA_DELAY)
        self.device.click_adb(*xy)
        self.device.sleep(max(float(delay), A.MIN_CLICK_INTERVAL))

    def _tap_sequence(self, clicks: list[tuple[int, int]], *, tag: str) -> None:
        prev: tuple[int, int] | None = None
        for i, pos in enumerate(clicks, 1):
            logger.info('AutoBreak %s %s/%s %s', tag, i, len(clicks), pos)
            self._tap(pos, prev=prev)
            prev = pos

    def _on_dock(self) -> bool:
        self.device.screenshot()
        matched = self.appear(
            GA.BOAT_AWAY_USE,
            offset=(12, 12),
            similarity=GA._TEMPLATE_SIMILARITY,
        )
        logger.info('AutoBreak BoatAwayUse match=%s (True=船坞页)', matched)
        return matched

    def _dock_list_empty(self) -> bool:
        self.device.screenshot()
        if os.path.isfile(GA.SEARCH_BOAT_NULL_FILE):
            matched = self.appear(
                GA.SEARCH_BOAT_NULL_BTN,
                offset=(20, 20),
                similarity=GA.SEARCH_BOAT_NULL_THRESHOLD,
            )
            logger.info('AutoBreak SearchBoatNull match=%s (True=空列表)', matched)
            return matched
        logger.warning('AutoBreak SEARCH_BOAT_NULL 模板缺失，跳过空船检测')
        return False

    def _enter_dock(self) -> bool:
        self.ui_goto_main()
        for attempt in range(1, GA._MAX_NAV_RETRY + 1):
            logger.info(
                'AutoBreak 进船坞 click=%s attempt=%s',
                A.CLICK_MAIN_TO_DOCK,
                attempt,
            )
            self._tap(A.CLICK_MAIN_TO_DOCK, delay=GA._AFTER_UI)
            self.device.sleep(GA._AFTER_UI)
            if self._on_dock():
                return True
            self.ui_goto_main()
        return False

    def _click_filter_keys(self, keys: List[FilterKey]) -> None:
        prev: tuple[int, int] | None = None
        for section, key in keys:
            slot = get_slot(section, key)
            xy = tuple(slot['click'])
            logger.info(
                'AutoBreak filter %s.%s (%s) %s',
                section,
                key,
                slot.get('label_zh', ''),
                xy,
            )
            self._tap(xy, delay=FSA._AFTER_FILTER_CLICK, prev=prev)
            prev = xy

    def _open_filter_panel(self) -> bool:
        for attempt in range(1, FSA._MAX_FILTER_OPEN_RETRY + 1):
            logger.info('AutoBreak 打开筛选 attempt=%s', attempt)
            self._tap(FSA.CLICK_OPEN_FILTER, delay=FSA._AFTER_FILTER_OPEN)
            self.device.screenshot()
            if self.appear(
                FSA.FILTER_CONFIRM,
                offset=FSA.FILTER_CONFIRM_OFFSET,
                similarity=FSA._TEMPLATE_SIMILARITY,
            ):
                return True
        return False

    def _confirm_filter_panel(self) -> None:
        if self.appear_then_click(
            FSA.FILTER_CONFIRM,
            offset=FSA.FILTER_CONFIRM_OFFSET,
            interval=FSA._CONFIRM_INTERVAL,
        ):
            self.device.sleep(FSA._AFTER_FILTER_DONE)
            return
        self._tap(FSA.CLICK_FILTER_CONFIRM_FALLBACK, delay=FSA._AFTER_FILTER_DONE)

    def _apply_dock_filters(self, rarity_key: str) -> bool:
        apply_keys = _build_break_filter_apply(rarity_key)
        logger.info(
            'AutoBreak 筛选 apply=%s 项 rarity_mode=%s',
            len(apply_keys),
            'all_except_ultra' if rarity_key == 'all' else rarity_key,
        )
        if not self._open_filter_panel():
            return False
        self._click_filter_keys(_FILTER_RESET)
        self._click_filter_keys(apply_keys)
        self._confirm_filter_panel()
        self.device.sleep(A._AFTER_FILTER)
        return True

    def _open_tupo_view(self) -> bool:
        """
        双搜索区流程：
          1. TupoInto 比对 slot1 + slot2，命中哪区点哪区中心
          2. TupoIntoYes 同样比对两区，任一命中即突破页
        """
        for attempt in range(1, A._MAX_TUPO_TAB_ATTEMPTS + 1):
            self.device.screenshot()
            into = pick_tupo_into_slot(self.device.image)
            if into is None:
                logger.warning('AutoBreak [1/2] TupoInto 两区均未命中 attempt=%s', attempt)
                self.device.sleep(A._AFTER_MATCH)
                continue

            center = tuple(int(x) for x in into['center'])
            logger.info(
                'AutoBreak [1/2] TupoInto slot=%s sim=%.4f 点 %s attempt=%s',
                into['slot'],
                into['sim'],
                center,
                attempt,
            )
            self._tap(center, delay=A._AFTER_TUPO_TAB)
            self.device.sleep(A._AFTER_MATCH)
            self.device.screenshot()

            yes = pick_tupo_into_yes_slot(self.device.image)
            if yes is not None:
                logger.info(
                    'AutoBreak [2/2] TupoIntoYes slot=%s sim=%.4f 验页成功 attempt=%s',
                    yes['slot'],
                    yes['sim'],
                    attempt,
                )
                return True
            logger.warning('AutoBreak [2/2] TupoIntoYes 两区均未命中 attempt=%s', attempt)

        logger.error('AutoBreak 未能完成 TupoInto → TupoIntoYes 进突破页')
        return False

    def _select_ship_and_open_tupo(self) -> bool:
        logger.info('AutoBreak 选船 %s', A.CLICK_SELECT_SHIP)
        self._tap(A.CLICK_SELECT_SHIP, delay=A._AFTER_DOCK)
        self.device.sleep(A._AFTER_MATCH)
        return self._open_tupo_view()

    def _run_tupo_do(self) -> None:
        self._tap_sequence(list(A.CLICKS_TUPO_DO), tag='TUPODO')

    def _return_to_dock(self) -> bool:
        logger.info('AutoBreak 点返回 %s', A.CLICK_BACK_DETAIL)
        self._tap(A.CLICK_BACK_DETAIL, delay=A._AFTER_DOCK)
        if self._on_dock():
            return True
        logger.warning('AutoBreak 首次返回未验到船坞，再点一次')
        self._tap(A.CLICK_BACK_DETAIL, delay=A._AFTER_DOCK)
        return self._on_dock()

    def _break_one_ship(self) -> bool:
        if not self._select_ship_and_open_tupo():
            logger.warning('AutoBreak 未能进入突破页')
            return False
        self._run_tupo_do()
        self.has_breakthrough = True
        self.breakthrough_count += 1
        logger.info('AutoBreak 突破完成 count=%s', self.breakthrough_count)
        if not self._return_to_dock():
            logger.warning('AutoBreak 突破后未能回到船坞')
        return True

    def _run_breakthrough_cycle(self, ships_target: int) -> None:
        for round_no in range(1, ships_target + 1):
            logger.info('AutoBreak 突破轮次 %s/%s', round_no, ships_target)
            if self._dock_list_empty():
                logger.info('AutoBreak 船坞空列表，停止')
                self.skipped_empty = True
                break
            if not self._break_one_ship():
                break
            if round_no >= ships_target:
                break
            logger.info('AutoBreak 下一艘仍点 %s', A.CLICK_SELECT_SHIP)

    def _return_main(self) -> None:
        logger.info('AutoBreak 返回主界面 %s', A.CLICK_RETURN_MAIN)
        self._tap(A.CLICK_RETURN_MAIN)
        self.ui_goto_main()

    def run(self) -> None:
        if gate_task_or_skip(self, 'ProalasAutoBreak'):
            return
        logger.hr('ProalasAutoBreak', level=1)
        config_name = self._config_name()
        rarity = parse_ship_rarity(self.config)
        ships_target = parse_ships_per_run(self.config)
        interval_days = parse_run_interval_days(self.config)
        self.breakthrough_count = 0
        self.has_breakthrough = False
        self.skipped_empty = False

        logger.info(
            'AutoBreak 配置 ShipRarity=%s (%s) ShipsPerRun=%s RunIntervalDays=%s',
            rarity,
            rarity_label_zh(rarity),
            ships_target,
            interval_days,
        )

        if not self._enter_dock():
            logger.error('AutoBreak 进入船坞失败')
            self.config.task_delay(success=False)
            return

        if not self._apply_dock_filters(rarity):
            logger.error('AutoBreak 船坞筛选失败')
            self.config.task_delay(success=False)
            return

        if self._dock_list_empty():
            self.skipped_empty = True
            logger.info('AutoBreak 筛选后无船可突破')
        else:
            self._run_breakthrough_cycle(ships_target)

        self._return_main()

        next_run = datetime.now().replace(microsecond=0) + timedelta(days=interval_days)
        self.config.task_delay(target=next_run, task='ProalasAutoBreak')

        write_auto_break_result(
            config_name,
            breakthrough_count=self.breakthrough_count,
            can_breakthrough=self.has_breakthrough,
            star_quality=rarity,
            config=self.config,
        )
        logger.info(
            'ProalasAutoBreak done device=%s rarity=%s count=%s empty_skip=%s next=%s',
            config_name,
            rarity,
            self.breakthrough_count,
            self.skipped_empty,
            next_run,
        )
