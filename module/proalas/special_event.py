# -*- coding: utf-8 -*-
"""
特殊活动处理 — 当前：竞拍场（Auction）

GambleType:
  LowYieldInterest  低倍策略吃息 — 不限中标，按「指定场次」或默认币选场，始终四位数
  ClaimQuestReward  完成任务 — 币≥8000k 则七位数(首位=QuestBidLevel 1~8)，否则四位数；
                    场次可由 VenueSelect 指定或默认规则；目前中标-初始≥TargetWins 后推迟 7 日
"""
from __future__ import annotations

import random
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from module.base.button import Button
from module.base.timer import Timer
from module.base.utils import load_image
from module.logger import logger
from module.ocr.ocr import Digit, Ocr
from module.proalas import auction_assets as A
from module.proalas.event_lifecycle import guard_task_or_delay
from module.ui.ui import UI

_TPL_CACHE: dict[str, Optional[np.ndarray]] = {}


def _parse_amount_text(raw: str) -> int:
    """解析竞拍币文案：7,289K / 7289k / 7289000 → int。"""
    if not raw:
        return -1
    s = str(raw).strip().replace(',', '').replace(' ', '').replace('，', '')
    s = s.replace('Ｏ', '0').replace('ｏ', '0')
    # 常见误读
    s = s.replace('s', '8').replace('S', '8').replace('g', '9').replace('B', '8')
    lower = s.lower()
    mult = 1
    if lower.endswith('k') or lower.endswith('κ') or lower.endswith('ｋ'):
        mult = 1000
        lower = lower[:-1]
    elif lower.endswith('m') or lower.endswith('ｍ'):
        mult = 1_000_000
        lower = lower[:-1]
    elif lower.endswith('万'):
        mult = 10_000
        lower = lower[:-1]
    cleaned = ''.join(ch for ch in lower if ch.isdigit() or ch == '.')
    if not cleaned or cleaned == '.':
        return -1
    try:
        val = float(cleaned) * mult
    except ValueError:
        return -1
    return int(val)


def _load_tpl(btn: Button) -> Optional[np.ndarray]:
    key = str(btn.file)
    if key not in _TPL_CACHE:
        try:
            _TPL_CACHE[key] = load_image(btn.file, area=None)
        except Exception as e:
            logger.warning('load tpl %s failed: %s', btn.name, e)
            _TPL_CACHE[key] = None
    return _TPL_CACHE[key]


def _click_xy(device, xy: Tuple[int, int], name: str = 'AUCTION_XY') -> None:
    x, y = xy
    btn = Button(
        area=(x - 8, y - 8, x + 8, y + 8),
        color=(0, 0, 0),
        button=(x - 8, y - 8, x + 8, y + 8),
        name=name,
    )
    device.click(btn)


class ProalasSpecialEvent(UI):
    def run(self):
        if not guard_task_or_delay(self.config, 'ProalasSpecialEvent'):
            return

        name = getattr(self.config, 'ProalasSpecialEvent_EventName', 'Auction')
        gamble = getattr(self.config, 'ProalasSpecialEvent_GambleType', 'LowYieldInterest')
        logger.hr('ProalasSpecialEvent', level=1)
        logger.info('event=%s gamble=%s', name, gamble)

        if name != 'Auction':
            logger.error('Unknown EventName=%s', name)
            self.config.task_delay(server_update=True)
            return

        if gamble == 'ClaimQuestReward':
            self._run_claim_quest_reward()
            return

        if gamble != 'LowYieldInterest':
            logger.error('Unknown GambleType=%s', gamble)
            self.config.task_delay(server_update=True)
            return

        self._run_low_yield_interest()

    # ---------------------------------------------------------- LowYieldInterest
    def _run_low_yield_interest(self) -> None:
        """低倍策略吃息：不限中标数，读完指标后持续开拍。"""
        logger.info('LowYieldInterest: no win cap, keep auctioning')
        self._auction_loop(mode='low_yield')

    # ---------------------------------------------------------- ClaimQuestReward
    def _run_claim_quest_reward(self) -> None:
        """完成任务：目前中标-初始中标≥TargetWins；币≥8000k 七位(首位=QuestBidLevel)，场次见 VenueSelect。"""
        target = self._quest_delta_target()
        logger.info(
            'ClaimQuestReward: delta_target=%s high_coin=%s venue=%s',
            target, A.QUEST_COIN_HIGH, self._venue_select(),
        )
        self._auction_loop(mode='quest')

    def _quest_delta_target(self) -> int:
        raw = getattr(self.config, 'ProalasSpecialEvent_TargetWins', None)
        try:
            v = int(raw)
        except (TypeError, ValueError):
            v = A.QUEST_WIN_DELTA
        return max(1, v if v > 0 else A.QUEST_WIN_DELTA)

    def _quest_lifecycle_tag(self) -> str:
        from module.proalas.event_lifecycle import TASK_LIFECYCLE
        return str(
            TASK_LIFECYCLE.get('ProalasSpecialEvent')
            or getattr(self.config, 'ProalasSpecialEvent_Lifecycle', '')
            or ''
        )

    def _ensure_quest_baseline(self, wins: int) -> int:
        """首次 OCR 写入初始中标；生命周期变更则重置。开关任务不重置。"""
        life = self._quest_lifecycle_tag()
        stored_life = str(getattr(self.config, 'ProalasSpecialEvent_QuestBaselineLifecycle', '') or '')
        try:
            baseline = int(getattr(self.config, 'ProalasSpecialEvent_QuestWinBaseline', -1))
        except (TypeError, ValueError):
            baseline = -1

        if stored_life != life:
            logger.info(
                'Quest lifecycle %r -> %r, reset baseline',
                stored_life, life,
            )
            baseline = -1

        if baseline < 0:
            baseline = max(0, int(wins))
            with self.config.multi_set():
                self.config.ProalasSpecialEvent_QuestWinBaseline = baseline
                self.config.ProalasSpecialEvent_QuestBaselineLifecycle = life
                self.config.ProalasSpecialEvent_QuestWinProgress = 0
            logger.info('QuestWinBaseline initialized to %s (lifecycle=%s)', baseline, life)
        return baseline

    def _quest_progress(self, wins: int) -> Tuple[int, int, int, bool]:
        """返回 (baseline, progress, target, done)。"""
        baseline = self._ensure_quest_baseline(wins)
        progress = max(0, int(wins) - baseline)
        target = self._quest_delta_target()
        done = progress >= target
        with self.config.multi_set():
            self.config.ProalasSpecialEvent_QuestWinProgress = int(progress)
        logger.info(
            'Quest progress baseline=%s current=%s delta=%s/%s done=%s',
            baseline, wins, progress, target, done,
        )
        return baseline, progress, target, done

    def _auction_loop(self, mode: str) -> None:
        """
        mode:
          low_yield — 不限中标；场次=VenueSelect 或默认币选；始终四位数
          quest     — 目前-初始≥TargetWins；币≥8000k→七位(首位=QuestBidLevel)否则四位；
                      场次=VenueSelect 或默认(高币默认 S，低币按币选)
        """
        rounds_cap = A.QUEST_ROUNDS_CAP if mode == 'quest' else A.ROUNDS_CAP

        if not self._enter_auction():
            logger.error('Enter auction failed — retry 5m')
            self.config.task_delay(minute=5)
            return

        coin, wins, joins = self._refresh_stats()
        if not getattr(self, '_stats_ocr_ok', False):
            logger.error('Auction stats OCR failed — retry 2m')
            self._leave_to_main()
            self.config.task_delay(minute=2)
            return

        if mode == 'quest':
            _b, _p, _t, done = self._quest_progress(wins)
            if done:
                logger.info('Quest already done delta≥target → delay 7 days')
                self._leave_to_main()
                self.config.task_delay(minute=7 * 24 * 60)
                return

        if not self._ensure_lobby():
            logger.error('Not in auction lobby after stats — retry 2m')
            self._leave_to_main()
            self.config.task_delay(minute=2)
            return

        venue0, _ = self._plan_round(mode, coin)
        if venue0 is None:
            logger.warning('Coins=%s cannot enter any venue — retry 30m', coin)
            self._leave_to_main()
            self.config.task_delay(minute=30)
            return

        finished_quest = False
        for round_i in range(1, rounds_cap + 1):
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            logger.hr(f'Auction round {round_i}/{rounds_cap} mode={mode}', level=2)

            if round_i > 1:
                coin, wins, joins = self._refresh_stats()
                if not self._ensure_lobby():
                    logger.warning('Lost lobby after stats, re-enter')
                    if not self._enter_auction():
                        break
                    coin, wins, joins = self._refresh_stats()

            if mode == 'quest':
                _b, progress, target, done = self._quest_progress(wins)
                if done:
                    logger.info('Quest delta reached %s/%s', progress, target)
                    finished_quest = True
                    break

            venue, bid_style = self._plan_round(mode, coin)
            if venue is None:
                logger.warning('Coins=%s insufficient for venue', coin)
                break

            if mode == 'quest':
                _b, progress, target, _d = self._quest_progress(wins)
                logger.info(
                    'Plan venue=%s bid=%s coin=%s wins=%s delta=%s/%s',
                    venue, bid_style, coin, wins, progress, target,
                )
            else:
                logger.info('Plan venue=%s bid=%s coin=%s wins=%s', venue, bid_style, coin, wins)
            self._bid_style = bid_style

            if not self._start_round(venue):
                logger.warning('Start round failed, retry enter')
                if not self._enter_auction():
                    break
                coin, wins, joins = self._refresh_stats()
                continue

            self._play_round_low_yield()
            time.sleep(1.0)
            if not self._wait_lobby_after_round():
                logger.warning('Not lobby after round — leave then re-enter')
                self._leave_to_main()
                if not self._enter_auction():
                    break
            coin, wins, joins = self._refresh_stats()
            logger.info('After round: coin=%s wins=%s joins=%s mode=%s', coin, wins, joins, mode)
            if mode == 'quest':
                _b, progress, target, done = self._quest_progress(wins)
                if done:
                    finished_quest = True
                    break
            if not self._ensure_lobby():
                continue
        else:
            logger.info('Auction round cap %s reached this run', rounds_cap)

        self._leave_to_main()
        if mode == 'quest' and finished_quest:
            logger.info('ClaimQuestReward done (delta≥target) → delay 7 days')
            self.config.task_delay(minute=7 * 24 * 60)
            return
        if mode == 'quest':
            coin, wins, joins = self._last_stats()
            _b, progress, target, _d = self._quest_progress(wins)
            logger.info(
                'ClaimQuestReward pause delta=%s/%s → retry 3m',
                progress, target,
            )
            self.config.task_delay(minute=3)
            return

        logger.info('LowYieldInterest pause → retry 3m')
        self.config.task_delay(minute=3)

    def _plan_round(self, mode: str, coin: int) -> Tuple[Optional[str], str]:
        """返回 (场次, 出价风格 low4|quest7)。"""
        bid_style = 'low4'
        if mode == 'quest' and coin >= A.QUEST_COIN_HIGH:
            bid_style = 'quest7'

        forced = self._venue_select()
        if forced in ('A', 'B', 'S'):
            if not self._can_enter_venue(forced, coin):
                logger.warning(
                    'Forced venue=%s but coin=%s < ticket — cannot enter',
                    forced, coin,
                )
                return None, bid_style
            logger.info('VenueSelect forced=%s (coin=%s bid=%s)', forced, coin, bid_style)
            return forced, bid_style

        # 默认规则
        if mode == 'quest' and coin >= A.QUEST_COIN_HIGH:
            logger.info('Default venue S (quest high coin=%s)', coin)
            return 'S', bid_style
        venue = self._pick_venue(coin)
        return venue, bid_style

    def _venue_select(self) -> str:
        raw = str(getattr(self.config, 'ProalasSpecialEvent_VenueSelect', 'Default') or 'Default')
        raw = raw.strip()
        if raw in ('A', 'B', 'S', 'Default'):
            return raw
        logger.warning('Invalid VenueSelect=%s, fallback Default', raw)
        return 'Default'

    def _can_enter_venue(self, venue: str, coin: int) -> bool:
        need = {'B': A.TICKET_B, 'A': A.TICKET_A, 'S': A.TICKET_S}.get(venue, 0)
        return coin >= need

    def _last_stats(self):
        return (
            int(getattr(self.config, 'ProalasSpecialEvent_AuctionCoin', 0) or 0),
            int(getattr(self.config, 'ProalasSpecialEvent_WinCount', 0) or 0),
            int(getattr(self.config, 'ProalasSpecialEvent_JoinCount', 0) or 0),
        )

    # ---------------------------------------------------------- navigation
    def _enter_auction(self) -> bool:
        from module.ui.page import page_main

        try:
            self.device.screenshot()
            if not self.ui_page_appear(page_main, offset=(20, 20)):
                # 可能卡在竞拍/结算未知页：先左上返回，再 ensure
                for i in range(A.LEAVE_BACK_TIMES):
                    _click_xy(self.device, A.LEAVE_BACK, name=f'AUCTION_PRE_ENTER_BACK_{i}')
                    time.sleep(A.LEAVE_BACK_GAP)
            self.ui_goto_main()
        except Exception as e:
            logger.error('Cannot reach main: %s', e)
            return False

        _click_xy(self.device, A.ENTER_CLICK_1, name='AUCTION_ENTER_1')
        time.sleep(A.ENTER_GAP_SEC)
        _click_xy(self.device, A.ENTER_CLICK_2, name='AUCTION_ENTER_2')
        time.sleep(2.0)
        self.device.screenshot()
        if self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is not None:
            logger.info('Entered auction lobby (JPmainview)')
            return True
        logger.warning('Entered auction but JPmainview not found (continue anyway)')
        return True

    def _finish_round_to_lobby(self) -> None:
        """识别 JPend(一键跳过) → 点模板区中心 → 再点退出(1090,640)回列表。"""
        logger.info('Round end: click JPend center %s then exit %s', A.JP_END_CLICK, A.ROUND_EXIT)
        _click_xy(self.device, A.JP_END_CLICK, name='AUCTION_JP_END_SKIP')
        time.sleep(1.2)
        _click_xy(self.device, A.ROUND_EXIT, name='AUCTION_ROUND_EXIT')
        time.sleep(1.5)

    def _wait_lobby_after_round(self) -> bool:
        """结算后等到「竞拍匹配」；勿调 ui_goto_main。"""
        for i in range(8):
            self.device.screenshot()
            if self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is not None:
                logger.info('Lobby ready after round (try=%s)', i)
                return True
            if self._find(A.JP_END, search=A.AREA_END, sim=A.MATCH_SIM_END) is not None:
                self._finish_round_to_lobby()
                continue
            # 可能已跳过、只剩退出键
            _click_xy(self.device, A.ROUND_EXIT, name=f'AUCTION_ROUND_EXIT_WAIT_{i}')
            time.sleep(1.2)
        return False

    def _leave_to_main(self) -> None:
        """竞拍界面回主：左上角 (40,45) 点两次。不调用会卡死的 ui_goto_main。"""
        logger.info('Leave auction → main: click (40,45) x%s', A.LEAVE_BACK_TIMES)
        self.device.click_record_clear()
        self.device.screenshot()
        if self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is None:
            _click_xy(self.device, A.STATS_BACK, name='AUCTION_STATS_BACK_BEFORE_LEAVE')
            time.sleep(0.8)
            # 结算残留：再试退出
            _click_xy(self.device, A.ROUND_EXIT, name='AUCTION_ROUND_EXIT_BEFORE_LEAVE')
            time.sleep(0.8)

        for i in range(A.LEAVE_BACK_TIMES):
            _click_xy(self.device, A.LEAVE_BACK, name=f'AUCTION_LEAVE_BACK_{i}')
            time.sleep(A.LEAVE_BACK_GAP)

        self.device.screenshot()
        try:
            from module.ui.page import page_main
            if self.ui_page_appear(page_main, offset=(20, 20)):
                logger.info('Back on page_main')
                return
        except Exception:
            pass
        logger.warning('Leave auction: skip ui_goto_main (avoid Unknown ui page hang)')

    def _ensure_lobby(self) -> bool:
        """确认在竞拍列表。"""
        self.device.screenshot()
        if self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is not None:
            return True
        _click_xy(self.device, A.STATS_BACK, name='AUCTION_STATS_BACK_ENSURE')
        time.sleep(1.0)
        self.device.screenshot()
        if self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is not None:
            return True
        _click_xy(self.device, A.ROUND_EXIT, name='AUCTION_ROUND_EXIT_ENSURE')
        time.sleep(1.0)
        self.device.screenshot()
        hit = self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is not None
        logger.info('Ensure lobby JPmainview=%s', hit)
        return hit

    def _pick_venue(self, coin: int) -> Optional[str]:
        """按持有虚拟币选场：<1000k→B，<3000k→A，≥3000k→S。"""
        if coin >= A.VENUE_COIN_S:
            venue = 'S'
        elif coin >= A.VENUE_COIN_A:
            venue = 'A'
        elif coin >= A.TICKET_B:
            venue = 'B'
        else:
            return None
        logger.info(
            'Pick venue %s (coin=%s thresholds A=%s S=%s)',
            venue, coin, A.VENUE_COIN_A, A.VENUE_COIN_S,
        )
        return venue

    def _venue_xy(self, venue: str) -> Tuple[int, int]:
        return {'B': A.VENUE_B, 'A': A.VENUE_A, 'S': A.VENUE_S}[venue]

    def _start_round(self, venue: str) -> bool:
        xy = self._venue_xy(venue)
        logger.info('Select venue %s @ %s', venue, xy)
        _click_xy(self.device, xy, name=f'AUCTION_VENUE_{venue}')
        time.sleep(0.8)
        _click_xy(self.device, A.START_AUCTION, name='AUCTION_START')
        time.sleep(A.POLL_SEC)

        for _ in range(12):
            self.device.screenshot()
            if self._find(A.JP_WAIT, search=A.AREA_WAIT) is not None:
                logger.info('Still waiting enter (JPwait), +%ss', int(A.POLL_SEC))
                time.sleep(A.POLL_SEC)
                continue
            if (
                self._find(A.JP_CHOOSE_BUFF, search=A.AREA_CHOOSE_BUFF) is not None
                or self._find(A.JP_BUY, search=A.AREA_BUY) is not None
                or self._find(A.JP_YES_PAY, search=A.AREA_YES_PAY) is not None
                or self._find(A.JP_END, search=A.AREA_END, sim=A.MATCH_SIM_END) is not None
            ):
                logger.info('Entered auction room')
                return True
            # 已离开列表（主界面按钮消失）也视为进场中
            if self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is None:
                logger.info('Left lobby UI, treat as entered')
                return True
            logger.info('No room UI yet, wait again')
            time.sleep(A.POLL_SEC)
        logger.warning('Enter auction room timeout')
        return False

    # ---------------------------------------------------------- round FSM
    def _play_round_low_yield(self) -> None:
        """局内：buff → 本轮出价 → 数字出价 → 一键跳过回列表。"""
        timeout = Timer(8 * 60, count=100).start()
        bid_done_this_cycle = False
        buy_clicks = 0

        while not timeout.reached():
            self.device.screenshot()

            # 1) 结算：一键跳过中心 → 退出(1090,640)
            if self._find(A.JP_END, search=A.AREA_END, sim=A.MATCH_SIM_END) is not None:
                self._finish_round_to_lobby()
                return

            # 2) Buff：只在标定区内匹配；确认点用死坐标，避免点到「本轮出价」
            if self._find(A.JP_CHOOSE_BUFF, search=A.AREA_CHOOSE_BUFF) is not None:
                logger.info('Choose buff → pick + confirm(fixed)')
                _click_xy(self.device, A.BUFF_PICK, name='AUCTION_BUFF_PICK')
                time.sleep(0.6)
                _click_xy(self.device, A.BUFF_CONFIRM, name='AUCTION_BUFF_CONFIRM')
                time.sleep(1.2)
                bid_done_this_cycle = False
                buy_clicks = 0
                continue

            # 3) 出价页
            if self._find(A.JP_YES_PAY, search=A.AREA_YES_PAY) is not None:
                if not bid_done_this_cycle:
                    self._do_bid()
                    bid_done_this_cycle = True
                    buy_clicks = 0
                time.sleep(A.POLL_SEC)
                continue

            # 4) 本轮出价（与主界面「竞拍匹配」同区，必须在局内且非列表）
            if self._find(A.JP_MAINVIEW, search=A.AREA_MAINVIEW) is not None:
                # 已回列表，本局结束
                logger.info('Back to lobby mid-round (JPmainview)')
                return
            if self._find(A.JP_BUY, search=A.AREA_BUY) is not None:
                if buy_clicks >= 3:
                    logger.warning('JPbuy clicked %s times without yespay — wait', buy_clicks)
                    time.sleep(A.POLL_SEC)
                    buy_clicks = 0
                    continue
                logger.info('Place bid button (JPbuy)')
                _click_xy(self.device, A.START_AUCTION, name='AUCTION_BUY')
                time.sleep(1.2)
                bid_done_this_cycle = False
                buy_clicks += 1
                continue

            time.sleep(A.POLL_SEC)

        logger.warning('Round timeout — force finish round')
        self._finish_round_to_lobby()

    def _do_bid(self) -> None:
        style = getattr(self, '_bid_style', 'low4')
        if style == 'quest7':
            self._bid_quest_seven()
        else:
            self._bid_random_four_digits()

    def _quest_bid_leading_digit(self) -> int:
        """完成任务高币七位数首位：配置 QuestBidLevel 1~8（一百万~八百万）。"""
        raw = getattr(self.config, 'ProalasSpecialEvent_QuestBidLevel', '4')
        try:
            d = int(str(raw).strip())
        except Exception:
            d = 4
        if d < 1 or d > 8:
            logger.warning('Invalid QuestBidLevel=%s, fallback to 4', raw)
            return 4
        return d

    def _bid_enter_digits(self, digits: list) -> None:
        """先归零再输入数字，再提交确认。"""
        _click_xy(self.device, A.BID_CLEAR, name='AUCTION_BID_CLEAR')
        time.sleep(0.35)
        logger.info('Bid digits (after clear): %s', ''.join(str(d) for d in digits))
        for d in digits:
            if d not in A.DIGIT_XY:
                logger.warning('No keypad for digit %s, skip', d)
                continue
            _click_xy(self.device, A.DIGIT_XY[d], name=f'AUCTION_DIGIT_{d}')
            time.sleep(0.25)
        _click_xy(self.device, A.BID_SUBMIT, name='AUCTION_BID_SUBMIT')
        # 确认弹窗出现较慢，短于 1s 容易点空卡住
        time.sleep(1.0)
        _click_xy(self.device, A.BID_CONFIRM, name='AUCTION_BID_CONFIRM')
        time.sleep(0.8)

    def _bid_random_four_digits(self) -> None:
        """低倍：随机 4 位（1-9）。"""
        self._bid_enter_digits([random.randint(1, 9) for _ in range(4)])

    def _bid_quest_seven(self) -> None:
        """完成任务高币：七位数，首位=QuestBidLevel(1~8)，后六位 1-9。低倍吃息不用此函数。"""
        lead = self._quest_bid_leading_digit()
        digits = [lead] + [random.randint(1, 9) for _ in range(6)]
        self._bid_enter_digits(digits)

    # ---------------------------------------------------------- match / OCR
    def _find(
        self,
        btn: Button,
        sim: float = None,
        search: Optional[Tuple[int, int, int, int]] = 'default',
    ) -> Optional[Tuple[int, int]]:
        """在 ROI 内 matchTemplate（search=None 全屏；'default' 用 btn.area）。"""
        if sim is None:
            sim = A.MATCH_SIM
        tpl = _load_tpl(btn)
        if tpl is None or tpl.size == 0:
            return None
        image = self.device.image
        if image is None:
            return None

        if search == 'default':
            search = btn.area
        if search is not None:
            x1, y1, x2, y2 = search
            # 外扩一点防裁切误差
            pad = 8
            x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
            x2, y2 = min(image.shape[1], x2 + pad), min(image.shape[0], y2 + pad)
            roi = image[y1:y2, x1:x2]
            ox, oy = x1, y1
        else:
            roi = image
            ox, oy = 0, 0

        if tpl.shape[0] > roi.shape[0] or tpl.shape[1] > roi.shape[1]:
            return None
        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _min_v, max_v, _min_l, max_loc = cv2.minMaxLoc(res)
        score = float(max_v)
        if np.isnan(score) or score < sim:
            return None
        th, tw = tpl.shape[:2]
        return (ox + max_loc[0] + tw // 2, oy + max_loc[1] + th // 2)

    def _ocr_digit(self, area, name: str) -> int:
        """中标/参与局数：浅底黑字，优先 cnocr。"""
        btn = Button(area=area, color=(0, 0, 0), button=area, name=name)
        letter = A.OCR_LETTER_BLACK
        try:
            ocr = Ocr(
                buttons=btn, lang='cnocr', letter=letter, threshold=128,
                alphabet=None, name=name,
            )
            raw = ocr.ocr(self.device.image)
            if isinstance(raw, list):
                raw = raw[0] if raw else ''
            raw = str(raw or '').strip()
            val = _parse_amount_text(raw)
            if val >= 0:
                logger.info('%s raw=%r -> %s', name, raw, val)
                return val
        except Exception as e:
            logger.warning('OCR %s cnocr failed: %s', name, e)
        try:
            dig = Digit(buttons=btn, lang='azur_lane', letter=letter, threshold=128, name=name)
            return int(dig.ocr(self.device.image) or 0)
        except Exception as e:
            logger.warning('OCR %s digit failed: %s', name, e)
            return -1

    def _ocr_auction_coin(self) -> int:
        """持有虚拟币：浅底黑字 cnocr，读 7,289K → 7289000。"""
        area = A.OCR_AUCTION_COIN
        btn = Button(area=area, color=(0, 0, 0), button=area, name='AUCTION_COIN')
        best_val = -1
        for letter in (A.OCR_LETTER_BLACK, (40, 40, 40), (30, 30, 30), (0, 0, 0)):
            try:
                ocr = Ocr(
                    buttons=btn, lang='cnocr', letter=letter, threshold=128,
                    alphabet=None, name='AUCTION_COIN',
                )
                raw = ocr.ocr(self.device.image)
                if isinstance(raw, list):
                    raw = raw[0] if raw else ''
                raw = str(raw or '').strip()
                val = _parse_amount_text(raw)
                logger.info('AUCTION_COIN raw=%r -> %s (letter=%s)', raw, val, letter)
                if val > best_val:
                    best_val = val
                if val >= A.TICKET_B and 'k' in raw.lower():
                    return val
            except Exception as e:
                logger.warning('AUCTION_COIN ocr failed letter=%s: %s', letter, e)

        if best_val >= A.TICKET_B:
            return best_val

        try:
            dig = Digit(
                buttons=btn, lang='azur_lane', letter=A.OCR_LETTER_BLACK,
                threshold=128, name='AUCTION_COIN_DIGIT',
            )
            num = int(dig.ocr(self.device.image) or 0)
            if num >= 1000:
                scaled = num * 1000
                logger.warning('AUCTION_COIN digit=%s assume K → %s', num, scaled)
                return scaled
            if num > best_val:
                best_val = num
        except Exception as e:
            logger.warning('AUCTION_COIN digit fallback failed: %s', e)

        return best_val

    def _refresh_stats(self) -> Tuple[int, int, int]:
        """只开一次指标面板 → 同一张图读三个数 → 只关一次回到竞拍列表。"""
        self._stats_ocr_ok = False
        logger.info('Refresh auction stats (open once → OCR×3 on same shot → close once)')
        _click_xy(self.device, A.STATS_OPEN, name='AUCTION_STATS_OPEN')
        time.sleep(1.5)
        self.device.screenshot()

        coin = self._ocr_auction_coin()
        wins = self._ocr_digit(A.OCR_WIN_COUNT, 'AUCTION_WINS')
        joins = self._ocr_digit(A.OCR_JOIN_COUNT, 'AUCTION_JOINS')

        old_c, old_w, old_j = self._last_stats()
        if coin < 0:
            coin = old_c
        if wins < 0:
            wins = old_w
        if joins < 0:
            joins = old_j

        # coin=1 残读不算成功；要有真实币量或局数
        self._stats_ocr_ok = bool(coin >= A.TICKET_B or wins > 0 or joins > 0)
        logger.info(
            'Auction stats coin=%s wins=%s joins=%s ocr_ok=%s',
            coin, wins, joins, self._stats_ocr_ok,
        )
        with self.config.multi_set():
            self.config.ProalasSpecialEvent_AuctionCoin = int(max(0, coin))
            self.config.ProalasSpecialEvent_WinCount = int(max(0, wins))
            self.config.ProalasSpecialEvent_JoinCount = int(max(0, joins))

        _click_xy(self.device, A.STATS_BACK, name='AUCTION_STATS_BACK')
        time.sleep(1.2)
        self.device.screenshot()
        return int(coin), int(wins), int(joins)
