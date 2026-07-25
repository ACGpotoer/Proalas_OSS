# -*- coding: utf-8 -*-
"""
ProAlas autoGetEXP + autoUseEXP（Alas 原生）。

流程见 module/GetExpUseExp/assets.py 与迁移文档 2026-06-14-自动获取使用经验书.md
"""
from __future__ import annotations

from datetime import datetime

from module.GetExpUseExp import assets as A
from module.logger import logger
from module.proalas.auto_break_ocr import find_text_click_point
from module.proalas.fleet_ocr import ocr_thin_digits
from module.proalas_collector.userdata import read_exp_book_value, write_exp_book_result
from module.ui.ui import UI

class ProalasGetExpUseExp(UI):
    exp_value: int = 0
    used_exp: bool = False
    got_exp: bool = False

    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _max_get_per_day(self) -> int:
        try:
            return max(0, int(getattr(self.config, 'ProalasGetExpUseExp_MaxGetPerDay', 1) or 1))
        except (TypeError, ValueError):
            return 1

    def _run_use_exp(self) -> bool:
        raw = getattr(self.config, 'ProalasGetExpUseExp_RunUseExp', True)
        if isinstance(raw, str):
            return raw.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(raw)

    def _use_exp_threshold(self) -> int:
        try:
            return int(getattr(self.config, 'ProalasGetExpUseExp_UseExpThreshold', 2000) or 2000)
        except (TypeError, ValueError):
            return 2000

    def _tap(
        self,
        xy: tuple[int, int],
        *,
        delay: float = A._AFTER_CLICK,
        prev: tuple[int, int] | None = None,
    ) -> None:
        if prev is not None and prev == xy:
            logger.info('GetExpUseExp 连续同坐标 %s，额外等待 %ss', xy, A._SAME_POS_EXTRA_DELAY)
            self.device.sleep(A._SAME_POS_EXTRA_DELAY)
        self.device.click_adb(*xy)
        self.device.sleep(max(float(delay), A.MIN_CLICK_INTERVAL))

    def _find_text_and_tap(self, text: str, *, round_idx: int) -> bool:
        target = str(text or '').strip()
        for attempt in range(1, A._FIND_TEXT_MAX_ATTEMPTS + 1):
            self.device.screenshot()
            pos = find_text_click_point(
                self.device.image,
                A.YANXI_LIST_AREA,
                target,
                row_count=A.YANXI_LIST_ROW_COUNT,
                name=f'GETEXP_{target}_R{round_idx}_T{attempt}',
            )
            if pos:
                logger.info('GetExpUseExp 命中「%s」 attempt=%s click=%s', target, attempt, pos)
                self._tap(pos)
                return True
            if attempt < A._FIND_TEXT_MAX_ATTEMPTS:
                logger.info(
                    'GetExpUseExp 第 %s/3 击未识别「%s」，%ss 后重试',
                    round_idx,
                    target,
                    A._FIND_TEXT_INTERVAL,
                )
                self.device.sleep(A._FIND_TEXT_INTERVAL)
        logger.warning('GetExpUseExp 第 %s/3 击 OCR 均未识别「%s」', round_idx, target)
        return False

    def _read_exp(self) -> int:
        self.device.screenshot()
        val = ocr_thin_digits(
            self.device.image,
            A.EXP_AREA,
            name='GETEXP_VALUE',
            scale=A.EXP_OCR_SCALE,
            lo=0,
            hi=999999,
        )
        return int(val or 0)

    def _return_main(self, *, from_detail: bool) -> None:
        clicks = A.RETURN_TO_MAIN_CLICKS if from_detail else A.RETURN_FROM_LIST_CLICKS
        label = '详情页' if from_detail else '列表页(无演习)'
        for i, pos in enumerate(clicks, 1):
            logger.info('GetExpUseExp 返回主界面(%s) %s/%s %s', label, i, len(clicks), pos)
            self._tap(pos)

    def _run_get_exp(self) -> int:
        for i, pos in enumerate(A.CLICKS_PREFIX, 1):
            logger.info('GetExpUseExp 导航 %s/%s %s', i, len(A.CLICKS_PREFIX), pos)
            self._tap(pos)

        exp_value = 0
        found_yanxi = False
        for i, pos in enumerate(A.LAST_THREE_CLICKS, 1):
            logger.info('GetExpUseExp 最后三击 %s/3 %s', i, pos)
            self._tap(pos)
            self.device.sleep(A._AFTER_NAV)
            if not self._find_text_and_tap(A.TARGET_TEXT, round_idx=i):
                continue
            found_yanxi = True
            self.device.sleep(1.0)
            exp_value = self._read_exp()
            self.exp_value = exp_value
            logger.info('GetExpUseExp 第 %s 轮 EXP=%s', i, exp_value)
            self._return_main(from_detail=True)
            self.got_exp = True
            break

        if not found_yanxi:
            logger.info(
                'GetExpUseExp 三击均未识别「%s」，按 EXP=0 处理',
                A.TARGET_TEXT,
            )
            exp_value = 0
            self.exp_value = 0
            self.got_exp = True
            self._return_main(from_detail=False)

        return exp_value

    def _run_use_exp_clicks(self) -> None:
        prev: tuple[int, int] | None = None
        for i, pos in enumerate(A.USE_EXP_CLICKS, 1):
            logger.info('GetExpUseExp useEXP 点击 %s/%s %s', i, len(A.USE_EXP_CLICKS), pos)
            self._tap(pos, prev=prev)
            prev = pos
        self.used_exp = True

    def _today_get_count(self) -> int:
        from module.proalas_collector.userdata import read_exp_book_meta

        meta = read_exp_book_meta(self._config_name())
        today = datetime.now().strftime('%Y-%m-%d')
        if str(meta.get('todayDate') or '') != today:
            return 0
        try:
            return int(meta.get('todayGetCount') or 0)
        except (TypeError, ValueError):
            return 0

    def run(self):
        logger.hr('ProalasGetExpUseExp', level=1)
        config_name = self._config_name()
        self.exp_value = 0
        self.used_exp = False
        self.got_exp = False

        self.ui_goto_main()

        max_day = self._max_get_per_day()
        today_count = self._today_get_count()
        if max_day > 0 and today_count >= max_day:
            logger.info(
                'GetExpUseExp 已达每日获取上限 %s（今日 %s），跳过获取',
                max_day,
                today_count,
            )
            self.exp_value = read_exp_book_value(config_name)
        else:
            self.exp_value = self._run_get_exp()

        threshold = self._use_exp_threshold()
        if self._run_use_exp() and self.exp_value > threshold:
            logger.info(
                'GetExpUseExp EXP=%s > 阈值 %s，执行 useEXP',
                self.exp_value,
                threshold,
            )
            self.ui_goto_main()
            self._run_use_exp_clicks()
        else:
            logger.info(
                'GetExpUseExp 跳过 useEXP: run=%s exp=%s threshold=%s',
                self._run_use_exp(),
                self.exp_value,
                threshold,
            )

        write_exp_book_result(
            config_name,
            exp_value=self.exp_value,
            got_exp=self.got_exp,
            used_exp=self.used_exp,
            threshold=threshold,
            config=self.config,
        )
        logger.info(
            'ProalasGetExpUseExp done device=%s exp=%s got=%s used=%s',
            config_name,
            self.exp_value,
            self.got_exp,
            self.used_exp,
        )
        self.config.task_delay(server_update=True)
