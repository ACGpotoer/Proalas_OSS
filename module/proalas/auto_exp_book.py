# -*- coding: utf-8 -*-
"""
ProAlas 自动使用经验书。

主界面 → 船坞 → 筛选（全部 / 全阵营 / 品质 / 未满级）→ 选船喂食 → 模板验回船坞，重复 N 轮。
"""
from __future__ import annotations

import os
import time
from typing import List, Tuple

import cv2

from module.AutoExpBook import assets as A
from module.GachaUp import assets as GA
from module.base.utils import crop, load_image
from module.logger import logger
from module.proalas import fleet_swap_assets as FSA
from module.proalas.auto_exp_book_config import (
    parse_feed_rounds,
    parse_run_interval_days,
    parse_ship_rarity,
    rarity_label_zh,
)
from module.proalas.dock_filter_map import get_slot
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas_collector.userdata import write_auto_exp_book_result
from module.ui.ui import UI

FilterKey = Tuple[str, str]

_FILTER_RESET: List[FilterKey] = [
    ('index', 'all'),
    ('faction', 'all'),
    ('rarity', 'all'),
    ('extra', 'no_limit'),
]


def _build_filter_apply(rarity_key: str) -> List[FilterKey]:
    keys: List[FilterKey] = []
    if rarity_key and rarity_key != 'all':
        keys.append(('rarity', rarity_key))
    keys.append(('extra', 'not_level_max'))
    return keys


class ProalasAutoExpBook(UI):
    feed_rounds_done: int = 0
    dock_empty: bool = False
    status: str = 'idle'
    status_label: str = ''

    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _tap(
        self,
        xy: tuple[int, int],
        *,
        delay: float = A._AFTER_TAP,
        prev: tuple[int, int] | None = None,
    ) -> None:
        if prev is not None and prev == xy:
            self.device.sleep(0.2)
        self.device.click_adb(*xy)
        self.device.sleep(max(float(delay), A._MIN_CLICK_INTERVAL))

    def _match_area_template(
        self,
        file: str,
        area: tuple[int, int, int, int],
        *,
        similarity: float,
        tag: str,
    ) -> bool:
        self.device.screenshot()
        template = load_image(file, area)
        search = crop(self.device.image, area, copy=False)
        if template.shape != search.shape:
            logger.warning(
                'AutoExpBook %s size mismatch tpl=%s search=%s',
                tag,
                template.shape,
                search.shape,
            )
            return False
        res = cv2.matchTemplate(template, search, cv2.TM_CCOEFF_NORMED)
        sim = float(res[0, 0]) if res.size == 1 else float(res.max())
        matched = sim > similarity
        logger.info(
            'AutoExpBook %s sim=%.4f match=%s need>%.2f',
            tag,
            sim,
            matched,
            similarity,
        )
        return matched

    def _on_dock(self) -> bool:
        self.device.screenshot()
        matched = self.appear(
            GA.BOAT_AWAY_USE,
            offset=(12, 12),
            similarity=GA._TEMPLATE_SIMILARITY,
        )
        logger.info('AutoExpBook BoatAwayUse match=%s (True=船坞页)', matched)
        return matched

    def _dock_list_empty(self) -> bool:
        self.device.screenshot()
        if os.path.isfile(GA.SEARCH_BOAT_NULL_FILE):
            matched = self.appear(
                GA.SEARCH_BOAT_NULL_BTN,
                offset=(20, 20),
                similarity=GA.SEARCH_BOAT_NULL_THRESHOLD,
            )
            logger.info('AutoExpBook SearchBoatNull match=%s (True=无可喂食舰)', matched)
            return matched
        logger.warning('AutoExpBook SEARCH_BOAT_NULL 模板缺失，跳过空船检测')
        return False

    def _enter_dock(self) -> bool:
        self.ui_goto_main()
        for attempt in range(1, GA._MAX_NAV_RETRY + 1):
            logger.info(
                'AutoExpBook 进船坞 click=%s attempt=%s',
                GA.CLICK_MAIN_TO_DOCK,
                attempt,
            )
            self._tap(GA.CLICK_MAIN_TO_DOCK, delay=GA._AFTER_UI)
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
                'AutoExpBook filter %s.%s (%s) %s',
                section,
                key,
                slot.get('label_zh', ''),
                xy,
            )
            self._tap(xy, delay=FSA._AFTER_FILTER_CLICK, prev=prev)
            prev = xy

    def _open_filter_panel(self) -> bool:
        for attempt in range(1, FSA._MAX_FILTER_OPEN_RETRY + 1):
            logger.info('AutoExpBook 打开筛选 attempt=%s', attempt)
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
        apply_keys = _build_filter_apply(rarity_key)
        if not self._open_filter_panel():
            return False
        self._click_filter_keys(_FILTER_RESET)
        self._click_filter_keys(apply_keys)
        self._confirm_filter_panel()
        self.device.sleep(A._AFTER_FILTER)
        return True

    def _maybe_confirm_aboard(self) -> None:
        deadline = time.time() + A._ABOARD_CONFIRM_POLL
        while time.time() < deadline:
            self.device.sleep(A._ABOARD_CONFIRM_POLL_STEP)
            if self._match_area_template(
                FSA.SHIP_ABOARD_CONFIRM_FILE,
                FSA.SHIP_ABOARD_CONFIRM_AREA,
                similarity=FSA._ABOARD_CONFIRM_SIMILARITY,
                tag='ShipAboardConfirm',
            ):
                logger.info(
                    'AutoExpBook 点确认弹窗 %s',
                    FSA.SHIP_ABOARD_CONFIRM_CENTER,
                )
                self.device.click_adb(*FSA.SHIP_ABOARD_CONFIRM_CENTER)
                self.device.sleep(FSA._AFTER_CONFIRM)
                return
        logger.info('AutoExpBook 无确认弹窗，喂食步骤结束')

    def _run_feed_clicks(self) -> None:
        prev: tuple[int, int] | None = None
        for i, pos in enumerate(A.FEED_CLICKS, 1):
            logger.info('AutoExpBook 喂食点击 %s/%s %s', i, len(A.FEED_CLICKS), pos)
            self._tap(pos, delay=A._AFTER_FEED, prev=prev)
            prev = pos
        self._maybe_confirm_aboard()

    def _return_to_dock(self) -> bool:
        logger.info('AutoExpBook 点返回 %s', A.CLICK_BACK_DETAIL)
        self._tap(A.CLICK_BACK_DETAIL, delay=A._AFTER_BACK)
        return self._on_dock()

    def _feed_one_round(self) -> bool:
        if self._dock_list_empty():
            return False
        self._run_feed_clicks()
        if not self._return_to_dock():
            logger.warning('AutoExpBook 喂食后未回到船坞，再点一次返回')
            self._tap(A.CLICK_BACK_DETAIL, delay=A._AFTER_BACK)
        return self._on_dock()

    def run(self) -> None:
        if gate_task_or_skip(self, 'ProalasAutoExpBook'):
            return
        logger.hr('ProalasAutoExpBook', level=1)

        rarity = parse_ship_rarity(self.config)
        rounds_target = parse_feed_rounds(self.config)
        interval_days = parse_run_interval_days(self.config)
        rarity_zh = rarity_label_zh(rarity)

        logger.info(
            'AutoExpBook config rarity=%s (%s) rounds=%s intervalDays=%s',
            rarity,
            rarity_zh,
            rounds_target,
            interval_days,
        )

        self.feed_rounds_done = 0
        self.dock_empty = False
        self.status = 'nav_failed'
        self.status_label = '进入船坞失败'

        if not self._enter_dock():
            write_auto_exp_book_result(
                self._config_name(),
                feed_rounds_target=rounds_target,
                feed_rounds_done=0,
                ship_rarity=rarity,
                status=self.status,
                status_label=self.status_label,
                config=self.config,
            )
            self.config.task_delay(success=False)
            return

        if not self._apply_dock_filters(rarity):
            self.status = 'filter_failed'
            self.status_label = '船坞筛选失败'
            write_auto_exp_book_result(
                self._config_name(),
                feed_rounds_target=rounds_target,
                feed_rounds_done=0,
                ship_rarity=rarity,
                status=self.status,
                status_label=self.status_label,
                config=self.config,
            )
            self.config.task_delay(success=False)
            return

        if self._dock_list_empty():
            self.dock_empty = True
            self.status = 'empty_dock'
            self.status_label = f'当前品质「{rarity_zh}」下无可喂食经验书的船只'
            logger.info('AutoExpBook %s', self.status_label)
            write_auto_exp_book_result(
                self._config_name(),
                feed_rounds_target=rounds_target,
                feed_rounds_done=0,
                ship_rarity=rarity,
                status=self.status,
                status_label=self.status_label,
                config=self.config,
            )
            self.ui_goto_main()
            self.config.task_delay(server_update=True)
            return

        for round_no in range(1, rounds_target + 1):
            logger.info('AutoExpBook 喂食轮次 %s/%s', round_no, rounds_target)
            if not self._feed_one_round():
                self.dock_empty = True
                self.status = 'empty_dock'
                self.status_label = (
                    f'第 {round_no} 轮前检测到空列表：'
                    f'品质「{rarity_zh}」下无可喂食船只'
                )
                logger.info('AutoExpBook %s', self.status_label)
                break
            self.feed_rounds_done += 1

        if self.feed_rounds_done >= rounds_target:
            self.status = 'ok'
            self.status_label = f'已完成 {self.feed_rounds_done} 轮经验书喂食'
        elif not self.dock_empty:
            self.status = 'partial'
            self.status_label = (
                f'完成 {self.feed_rounds_done}/{rounds_target} 轮后未能确认回到船坞'
            )

        write_auto_exp_book_result(
            self._config_name(),
            feed_rounds_target=rounds_target,
            feed_rounds_done=self.feed_rounds_done,
            ship_rarity=rarity,
            status=self.status,
            status_label=self.status_label,
            config=self.config,
        )
        logger.info(
            'ProalasAutoExpBook done device=%s rounds=%s/%s status=%s',
            self._config_name(),
            self.feed_rounds_done,
            rounds_target,
            self.status_label,
        )
        self.ui_goto_main()
        from datetime import datetime, timedelta

        next_run = datetime.now() + timedelta(days=interval_days)
        self.config.task_delay(target=next_run, task='ProalasAutoExpBook')
