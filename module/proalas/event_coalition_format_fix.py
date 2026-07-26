# -*- coding: utf-8 -*-
"""
共斗活动（怪谈纪实 coalition_20260723）开荒检测与配队修正。

无星判定：
- 非末关：地图上「下一关已出现」→ 本关已通
- SP：「今日次数: 0/1」→ 视为已通关 SP，不进关
- 末关 / 下一关未出现：进配队页看空队
配队顺序（normal/hard 多队）：
  1) 先切「单队连战」并确认有队（空则推荐）
  2) 再切「多队出击」
  3) 再逐队 I…N 空检+推荐（不上潜艇）
全通后刷 hard 前同样走完整配队，再交 Coalition；自检推迟约 7 天。
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

import cv2
import numpy as np

from module.base.button import Button
from module.base.timer import Timer
from module.base.utils import crop
from module.coalition.assets import (
    HORROR_EASY,
    HORROR_FLEET_PREPARATION,
    HORROR_HARD,
    HORROR_NORMAL,
    HORROR_SP,
    NEONCITY_PREPARATION_EXIT,
    PROALAS_HORROR_SP_COUNT_ZERO,
    PROALAS_NULL_BOAT_IN_FLEET,
)
from module.exception import RequestHumanTakeover
from module.logger import logger

COALITION_PUSH_STAGES = ('easy', 'normal', 'hard', 'sp')

# 怪谈纪实配队页「队伍 I–IV」点击中心（不上潜艇）
HORROR_FLEET_TAB_CLICKS = (
    (118, 152),
    (263, 152),
    (404, 152),
    (536, 152),
)
HORROR_FLEET_TAB_BOXES = (
    (75, 136, 165, 168),
    (220, 136, 310, 168),
    (360, 136, 450, 168),
    (490, 136, 580, 168),
)
HORROR_RECOMMEND_CLICK = (800, 255)

_STAGE_BUTTON = {
    'easy': HORROR_EASY,
    'normal': HORROR_NORMAL,
    'hard': HORROR_HARD,
    'sp': HORROR_SP,
}

_STOP_STAGE_ALIASES = {
    'easy': 'easy',
    'e': 'easy',
    '简单': 'easy',
    '单人病房': 'easy',
    'normal': 'normal',
    'n': 'normal',
    '普通': 'normal',
    'icu': 'normal',
    'icu病房': 'normal',
    'hard': 'hard',
    'h': 'hard',
    '困难': 'hard',
    '护士办公': 'hard',
    '护士办公室': 'hard',
    'sp': 'sp',
    's.p': 'sp',
    '地下室': 'sp',
    'sp地下室': 'sp',
}


def is_coalition_event(event_folder: str) -> bool:
    return str(event_folder or '').startswith('coalition_')


def parse_stop_stage(raw) -> Optional[str]:
    text = str(raw or '').strip().lower().replace(' ', '').replace('.', '')
    if not text:
        return None
    # normalize s.p / S.P
    text = text.replace('s.p', 'sp')
    if text in _STOP_STAGE_ALIASES:
        return _STOP_STAGE_ALIASES[text]
    # try without punctuation
    key = str(raw or '').strip().lower()
    if key in _STOP_STAGE_ALIASES:
        return _STOP_STAGE_ALIASES[key]
    logger.warning('EventFormatFix StopStage %r not recognized, ignore', raw)
    return None


def stages_until_stop(stop_stage: Optional[str]) -> List[str]:
    if not stop_stage:
        return list(COALITION_PUSH_STAGES)
    if stop_stage not in COALITION_PUSH_STAGES:
        return list(COALITION_PUSH_STAGES)
    end = COALITION_PUSH_STAGES.index(stop_stage)
    return list(COALITION_PUSH_STAGES[: end + 1])


def fleet_mode_for_stage(stage: str, config=None) -> str:
    """
    怪谈纪实配队规则：
    - easy：强制单队
    - normal/hard：默认 multi（普通2队/困难3队）；配置 single 仅影响开战，补队逻辑另走
    - sp：强制多队
    """
    stage = stage.lower()
    if stage == 'easy':
        return 'single'
    if stage == 'sp':
        return 'multi'
    preferred = 'multi'
    if config is not None:
        preferred = str(
            getattr(config, 'Coalition_Fleet', None)
            or config.cross_get('Coalition.Coalition.Fleet', 'multi')
            or 'multi'
        ).lower()
    if preferred not in ('single', 'multi'):
        preferred = 'multi'
    return preferred


def prepare_fleet_mode(stage: str) -> str:
    """开荒/补队专用：normal/hard/sp 一律按多队扫队，不被配置里残留的 single 带偏。"""
    stage = stage.lower()
    if stage == 'easy':
        return 'single'
    return 'multi'


def fleet_slot_count(stage: str, fleet_mode: str) -> int:
    """需要配置的水面舰队数量（不含潜艇）。"""
    stage = stage.lower()
    mode = str(fleet_mode or 'single').lower()
    if stage == 'easy' or mode == 'single':
        return 1
    if stage == 'normal':
        return 2
    if stage == 'hard':
        return 3
    if stage == 'sp':
        return 4
    return 1


def _tab_looks_present(image, box: Tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = box
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    # 有页签文字时对比度明显高于空白装饰
    return float(np.std(crop)) > 18.0


def _button_at(xy: Tuple[int, int], name: str = 'CLICK_XY', pad: int = 8) -> Button:
    """device.click 只接受 Button，不能传裸坐标元组。"""
    x, y = int(xy[0]), int(xy[1])
    area = (x - pad, y - pad, x + pad, y + pad)
    return Button(area=area, color=(128, 128, 128), button=area, name=name)


class CoalitionHorrorFormatFix(object):
    """Mixin-style helper; expects a Coalition (or CoalitionUI) instance as `main`."""

    def __init__(self, main):
        self.main = main

    def _click_xy(self, xy: Tuple[int, int], name: str = 'CLICK_XY') -> None:
        self.device.click(_button_at(xy, name=name))

    @property
    def config(self):
        return self.main.config

    @property
    def device(self):
        return self.main.device

    def _stage_appear(self, stage: str) -> bool:
        button = _STAGE_BUTTON[stage]
        # offset 开启时走模板匹配，应用 similarity（0~1），不是 color threshold
        return self.main.appear(button, offset=(40, 40), similarity=0.75)

    def _sp_count_exhausted(self) -> bool:
        """地图 SP 节点「今日次数: 0/1」→ 当日次数已用尽，不可再进。"""
        PROALAS_HORROR_SP_COUNT_ZERO.resource_release()
        return self.main.appear(
            PROALAS_HORROR_SP_COUNT_ZERO, offset=(30, 20), similarity=0.75
        )

    def _in_fleet_prep(self) -> bool:
        return self.main.appear(HORROR_FLEET_PREPARATION, offset=(30, 40), similarity=0.7)

    def _null_boat_similarity(self) -> float:
        """当前截图相对空队模板的匹配分（调试/判定用）。"""
        button = PROALAS_NULL_BOAT_IN_FLEET
        # 资源若曾被 load 成坏图（裁切越界全黑），强制重载
        button.ensure_template()
        if button.image is None or float(np.mean(button.image)) < 1.0:
            button.resource_release()
            button.ensure_template()
        offset = np.array((-20, -20, 20, 20))
        image = crop(self.device.image, offset + np.array(button.area), copy=False)
        res = cv2.matchTemplate(button.image, image, cv2.TM_CCOEFF_NORMED)
        return float(cv2.minMaxLoc(res)[1])

    def _dump_null_boat_roi(self, tag: str, sim: float) -> None:
        """把比对区抠出来，便于核对误检。"""
        if getattr(self, '_null_roi_dumped', False):
            return
        try:
            import os
            x1, y1, x2, y2 = PROALAS_NULL_BOAT_IN_FLEET.area
            roi = self.device.image[y1:y2, x1:x2]
            folder = os.path.join('.', 'log', 'coalition_null_boat')
            os.makedirs(folder, exist_ok=True)
            name = 'null_roi_%s_sim%.3f.png' % (tag, sim)
            cv2.imwrite(os.path.join(folder, name), roi)
            # 同时 dump 当前内存里的模板，确认不是全黑
            tpl = PROALAS_NULL_BOAT_IN_FLEET.image
            if tpl is not None:
                cv2.imwrite(os.path.join(folder, 'null_tpl_in_memory.png'), tpl)
            self._null_roi_dumped = True
            logger.info('CoalitionFormatFix dumped null ROI → %s/%s (tpl_mean=%.1f)',
                        folder, name, float(tpl.mean()) if tpl is not None else -1)
        except Exception as e:
            logger.warning('CoalitionFormatFix dump null ROI failed: %s', e)

    def _is_null_boat(self) -> bool:
        # 修复后：满队 ~0.05，空队 ~1.0；全黑坏模板会恒为 1.0（已修资产）
        sim = self._null_boat_similarity()
        empty = sim > 0.85
        if empty:
            self._dump_null_boat_roi('hit', sim)
        return empty

    def _exit_fleet_prep(self) -> None:
        logger.info('CoalitionFormatFix exit fleet prep')
        timeout = Timer(20, count=40).start()
        while not timeout.reached():
            self.device.screenshot()
            if self.main.in_coalition():
                return
            if self.main.appear_then_click(NEONCITY_PREPARATION_EXIT, offset=(20, 20), interval=2):
                continue
            if self.main.appear(HORROR_FLEET_PREPARATION, offset=(30, 40)):
                self.device.click(NEONCITY_PREPARATION_EXIT)
                continue
        logger.warning('CoalitionFormatFix exit fleet prep timeout')

    def _enter_fleet_prep(self, event: str, stage: str) -> bool:
        button = self.main.coalition_get_entrance(event, stage)
        timeout = Timer(25, count=50).start()
        clicks = 0
        while not timeout.reached():
            self.device.screenshot()
            if self._in_fleet_prep():
                return True
            if self.main.handle_story_skip():
                continue
            if self.main.in_coalition() and self.main.appear_then_click(button, offset=(40, 40), interval=2):
                clicks += 1
                if clicks > 8:
                    logger.error('CoalitionFormatFix too many clicks entering %s', stage)
                    return False
                continue
        logger.error('CoalitionFormatFix enter prep timeout: %s', stage)
        return False

    def _click_recommend(self) -> None:
        self._click_xy(HORROR_RECOMMEND_CLICK, name='HORROR_RECOMMEND')

    def _wait_fleet_filled(self, timeout: int = 12) -> bool:
        limit = Timer(timeout, count=timeout * 2).start()
        while not limit.reached():
            self.device.screenshot()
            if not self._is_null_boat():
                return True
            time.sleep(0.25)
        self.device.screenshot()
        return not self._is_null_boat()

    def _recommend_until_filled(self, label: str, tries: int = 3) -> bool:
        """空队时点推荐；可连点几次（动画/确认）。"""
        for i in range(tries):
            self.device.screenshot()
            sim = self._null_boat_similarity()
            if not self._is_null_boat():
                logger.info('CoalitionFormatFix %s already filled (sim=%.3f)', label, sim)
                return True
            logger.info(
                'CoalitionFormatFix recommend %s try=%s/%s empty_sim=%.3f',
                label, i + 1, tries, sim,
            )
            self._click_recommend()
            time.sleep(1.2)
            if self._wait_fleet_filled(timeout=8):
                return True
        self.device.screenshot()
        sim = self._null_boat_similarity()
        ok = not self._is_null_boat()
        if not ok:
            logger.error(
                'CoalitionFormatFix recommend failed: %s still empty (sim=%.3f)',
                label, sim,
            )
        return ok

    def _ensure_single_multi(self, fleet: str) -> bool:
        """用原版 coalition_set_fleet（HORROR_SWITCH_* 色匹配），不离开配队页。"""
        if fleet not in ('single', 'multi'):
            return False
        try:
            self.device.screenshot()
            clicked = self.main.coalition_set_fleet('coalition_20260723', fleet)
            logger.info(
                'CoalitionFormatFix coalition_set_fleet(%s) clicked=%s',
                fleet, clicked,
            )
            time.sleep(0.4)
            self.device.screenshot()
            return True
        except Exception as e:
            logger.warning('CoalitionFormatFix coalition_set_fleet %s failed: %s', fleet, e)
            return False

    def _prepare_visible_fleets(self, stage: str, fleet: str) -> bool:
        """
        全程留在同一配队页，不退出重进：
        - normal/hard 多队：单队连战有队 → 原界面点多队出击 → 逐队推荐
        - easy：只处理单队
        - sp：无单多按钮，直接逐队
        """
        slots = fleet_slot_count(stage, fleet)
        logger.info(
            'CoalitionFormatFix prepare stage=%s fleet=%s slots=%s (stay on prep page)',
            stage, fleet, slots,
        )

        if stage in ('normal', 'hard') and slots > 1:
            if not self._ensure_single_multi('single'):
                logger.error('CoalitionFormatFix cannot enter 单队连战')
                return False
            if not self._recommend_until_filled('fleet1(单队连战)'):
                logger.error('CoalitionFormatFix 单队连战 empty, refuse 多队出击')
                return False
            # 原界面直接点多队出击，不退出
            if not self._ensure_single_multi('multi'):
                logger.error('CoalitionFormatFix cannot enter 多队出击')
                return False
            time.sleep(0.5)
            self.device.screenshot()
            return self._scan_recommend_fleet_tabs(slots)

        if slots <= 1:
            if stage in ('normal', 'hard'):
                self._ensure_single_multi('single')
            return self._recommend_until_filled('fleet1(single)')

        return self._scan_recommend_fleet_tabs(slots)

    def fill_fleets_on_prep_page(self, stage: str, mode: str = None) -> bool:
        """
        已在配队页时调用（FormatFix / Coalition.handle_fleet_preparation 共用）。
        不进不出页面；normal/hard 强制按多队补。
        """
        PROALAS_NULL_BOAT_IN_FLEET.resource_release()
        self._null_roi_dumped = False
        if mode is None:
            mode = prepare_fleet_mode(stage)
        return self._prepare_visible_fleets(stage, mode)

    def _scan_recommend_fleet_tabs(self, slots: int) -> bool:
        """多队出击界面：逐个点队伍 I…N，空则推荐。"""
        for idx in range(slots):
            click = HORROR_FLEET_TAB_CLICKS[idx]
            box = HORROR_FLEET_TAB_BOXES[idx]
            self.device.screenshot()
            if not _tab_looks_present(self.device.image, box):
                logger.warning(
                    'CoalitionFormatFix fleet tab %s/%s look weak, click anyway',
                    idx + 1, slots,
                )
            logger.info(
                'CoalitionFormatFix select fleet tab %s/%s click=%s',
                idx + 1, slots, click,
            )
            self._click_xy(click, name='FLEET_TAB_%s' % (idx + 1))
            time.sleep(0.6)
            self.device.screenshot()
            sim = self._null_boat_similarity()
            logger.info(
                'CoalitionFormatFix fleet tab %s/%s empty_sim=%.3f',
                idx + 1, slots, sim,
            )
            if not self._recommend_until_filled('fleet%s' % (idx + 1)):
                return False
        return True

    def _enter_prepare_all_fleets(self, event: str, stage: str, fleet_mode: str = None) -> bool:
        """进配队页并补齐该关全部水面舰队。normal/hard 补队强制 multi（2/3队）。"""
        if not self._enter_fleet_prep(event, stage):
            return False
        if fleet_mode is None:
            fleet_mode = prepare_fleet_mode(stage)
        ok = self._prepare_visible_fleets(stage, fleet_mode)
        self._exit_fleet_prep()
        return ok

    def _human_takeover_stop_stage(self, stage: str) -> None:
        """推荐失败：写入停止关卡（上一档可打）并人工接管。"""
        idx = COALITION_PUSH_STAGES.index(stage) if stage in COALITION_PUSH_STAGES else 0
        fallback = COALITION_PUSH_STAGES[idx - 1] if idx > 0 else ''
        with self.config.multi_set():
            self.config.ProalasEventFormatFix_StopStage = fallback
            self.config.ProalasEventFormatFix_AllCleared = False
        logger.critical(
            'CoalitionFormatFix recommend/stat failed at %s → StopStage=%r, human takeover',
            stage,
            fallback,
        )
        raise RequestHumanTakeover

    def _apply_coalition_push(self, event: str, stage: str) -> None:
        # 开荒开战：normal/hard/sp 用多队
        fleet = prepare_fleet_mode(stage)
        with self.config.multi_set():
            self.config.cross_set('Coalition.Campaign.Event', event)
            self.config.cross_set('Coalition.Coalition.Mode', stage)
            self.config.cross_set('Coalition.Coalition.Fleet', fleet)
            self.config.cross_set('Coalition.StopCondition.RunCount', 1)
            self.config.cross_set('Coalition.Scheduler.Enable', True)
            self.config.ProalasEventFormatFix_AllCleared = False
        logger.info(
            'CoalitionFormatFix push Coalition Mode=%s Fleet=%s slots=%s RunCount=1',
            stage,
            fleet,
            fleet_slot_count(stage, fleet),
        )
        self.config.task_call('Coalition')

    def _apply_coalition_farm_hard(self, event: str) -> None:
        with self.config.multi_set():
            self.config.cross_set('Coalition.Campaign.Event', event)
            self.config.cross_set('Coalition.Coalition.Mode', 'hard')
            self.config.cross_set('Coalition.Coalition.Fleet', 'multi')
            self.config.cross_set('Coalition.StopCondition.RunCount', 0)
            self.config.cross_set('Coalition.Scheduler.Enable', True)
            self.config.ProalasEventFormatFix_AllCleared = True
            # 清空停止关卡，避免卡住
            self.config.ProalasEventFormatFix_StopStage = ''
        logger.info('CoalitionFormatFix all cleared → farm hard, AllCleared=true')

    def _probe_stage_needs_clear(self, event: str, stage: str, stages: List[str]) -> Optional[bool]:
        """
        Returns:
            True: 需要开荒
            False: 已通关
            None: 无法判定 / 失败

        判定（怪谈无星）：
        1. 非末关且地图上「下一关已出现」→ 已通关（配队可被清空，空队不能当未通关）
        2. SP 且「今日次数: 0/1」→ 视为已通关 SP，不进关
        3. 末关 / 下一关未出现 → 进配队页：空队=要开荒，有船=已通关
        """
        idx = stages.index(stage)
        next_stage = stages[idx + 1] if idx + 1 < len(stages) else None
        next_missing = False
        if next_stage:
            next_missing = not self._stage_appear(next_stage)

        # 下一关已解锁：本关必已通，不必再看空队、也不进配队
        if next_stage and not next_missing:
            logger.info(
                'CoalitionFormatFix probe %s next=%s unlocked → treat cleared',
                stage,
                next_stage,
            )
            return False

        # SP 当日次数用尽：点进去进不了配队，直接当已通关，去刷 hard
        if stage == 'sp':
            self.device.screenshot()
            if self._sp_count_exhausted():
                logger.info(
                    'CoalitionFormatFix SP today count 0/1 → treat cleared, skip enter'
                )
                return False

        if not self._enter_fleet_prep(event, stage):
            # 进 SP 失败时再确认一次次数（避免模板偏移漏检）
            if stage == 'sp':
                self.device.screenshot()
                if self._sp_count_exhausted():
                    logger.info(
                        'CoalitionFormatFix enter SP failed but count=0 → treat cleared'
                    )
                    return False
            return None

        self.device.screenshot()
        empty = self._is_null_boat()
        sim = self._null_boat_similarity()
        logger.info(
            'CoalitionFormatFix probe %s empty=%s sim=%.3f next=%s next_missing=%s',
            stage,
            empty,
            sim,
            next_stage,
            next_missing,
        )
        self._exit_fleet_prep()
        if empty:
            return True
        return False

    def run(self, event: str) -> None:
        main = self.main
        if event != 'coalition_20260723':
            logger.warning(
                'CoalitionFormatFix only implemented for coalition_20260723, got %s — skip',
                event,
            )
            self.config.task_delay(server_update=True)
            return

        if bool(getattr(self.config, 'ProalasEventFormatFix_AllCleared', False)):
            logger.info(
                'CoalitionFormatFix AllCleared=true → ensure normal(2)+hard(3) fleets then delay 7d'
            )
            PROALAS_NULL_BOAT_IN_FLEET.resource_release()
            self._null_roi_dumped = False
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            main.ui_goto_coalition()
            main.coalition_ensure_mode(event, 'battle')
            # 普通、困难都要按多队补齐（不是只补困难）
            for stage in ('normal', 'hard'):
                if not self._enter_prepare_all_fleets(event, stage, fleet_mode='multi'):
                    logger.critical(
                        'CoalitionFormatFix AllCleared but %s multi-fleet prepare failed',
                        stage,
                    )
                    raise RequestHumanTakeover
            self.config.task_delay(minute=7 * 24 * 60)
            return

        stop = parse_stop_stage(getattr(self.config, 'ProalasEventFormatFix_StopStage', ''))
        stages = stages_until_stop(stop)
        logger.info('CoalitionFormatFix event=%s stages=%s stop=%s', event, stages, stop)

        # 清掉可能缓存的坏模板（旧裁切图越界→全黑→sim恒1.0）
        PROALAS_NULL_BOAT_IN_FLEET.resource_release()
        self._null_roi_dumped = False

        # 活动开荒期关掉主线（蓝区物化也应写；此处兜底）
        with self.config.multi_set():
            self.config.cross_set('Main.Scheduler.Enable', False)
            self.config.cross_set('Main2.Scheduler.Enable', False)

        self.device.stuck_record_clear()
        self.device.click_record_clear()
        main.ui_goto_coalition()
        main.coalition_ensure_mode(event, 'battle')
        self.device.screenshot()

        if 'easy' in stages and not self._stage_appear('easy'):
            logger.error('CoalitionFormatFix HORROR_EASY not found on map')
            raise RequestHumanTakeover

        for stage in stages:
            self.device.screenshot()
            if not self._stage_appear(stage):
                logger.info('CoalitionFormatFix stage %s not unlocked', stage)
                if stage == stages[0]:
                    raise RequestHumanTakeover
                target = stages[stages.index(stage) - 1]
                self._prepare_and_call(event, target)
                return

            need = self._probe_stage_needs_clear(event, stage, stages)
            if need is None:
                raise RequestHumanTakeover
            if not need:
                logger.info('CoalitionFormatFix %s has fleet → treat cleared', stage)
                continue

            self._prepare_and_call(event, stage)
            return

        # 全通后刷 hard：先把 hard 3 队补齐（强制 multi），再交 Coalition
        if not self._enter_prepare_all_fleets(event, 'hard', fleet_mode='multi'):
            logger.critical('CoalitionFormatFix farm hard: multi-fleet prepare failed')
            raise RequestHumanTakeover
        self._apply_coalition_farm_hard(event)
        self.config.task_call('Coalition')
        self.config.task_delay(minute=7 * 24 * 60)
        self.config.task_stop()

    def _prepare_and_call(self, event: str, stage: str) -> None:
        # 开荒开战前补队：normal/hard 强制按多队扫（2/3），不被 config single 吃掉
        fleet = prepare_fleet_mode(stage)
        if not self._enter_prepare_all_fleets(event, stage, fleet_mode=fleet):
            self._human_takeover_stop_stage(stage)
        self._apply_coalition_push(event, stage)
        self.config.task_delay(minute=1)
        self.config.task_stop()
