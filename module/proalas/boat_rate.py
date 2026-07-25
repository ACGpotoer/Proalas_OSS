# -*- coding: utf-8 -*-
"""Alas 原生：主界面 → 检测 RateArea_Get → 收藏页 OCR → 写入 ./config/{name}.json。"""
from __future__ import annotations

from module.BoatRate.assets import RATE_AREA_GET
from module.logger import logger
from module.ocr.ocr import Ocr, OcrYuv
from module.proalas.collection_rate_parse import parse_collection_rate_percent
from module.proalas_collector.userdata import read_boat_max, write_boat_rate
from module.ui.ui import UI

_FIRST_NAV_CLICK = (980, 560)
_RETURN_MAIN = (1230, 30)
_NAV_DETECT_ATTEMPTS = 3
_AFTER_RATE_PAGE = 2.0
_AFTER_CLICK_DETECT = 0.8
_OCR_RETRY = 3
_OCR_RETRY_INTERVAL = 0.7

_RATE_OCR_KW = dict(
    letter=(255, 247, 200),
    threshold=128,
    alphabet='0123456789',
    name='COLLECTION_RATE',
)
# YUV 在本机更稳，优先尝试
OCR_COLLECTION_RATE_YUV = OcrYuv([(970, 10, 1050, 45)], **_RATE_OCR_KW)
OCR_COLLECTION_RATE = Ocr([(970, 10, 1050, 45)], **_RATE_OCR_KW)
OCR_COLLECTION_RATE_LO = Ocr([(970, 10, 1050, 45)], letter=(255, 247, 200), threshold=96, alphabet='0123456789', name='COLLECTION_RATE_LO')


def _normalize_rate_digits(raw) -> str:
    if raw is None:
        return ''
    text = str(raw).strip()
    text = (
        text.replace('I', '1')
        .replace('O', '0')
        .replace('D', '0')
        .replace('S', '5')
        .replace('B', '8')
    )
    return ''.join(c for c in text if c.isdigit())


class ProalasBoatMessage(UI):
    """采集收藏率 BoatRate（解析规则同 PA getBoatMessage）。"""

    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _open_collection_page(self) -> bool:
        for attempt in range(1, _NAV_DETECT_ATTEMPTS + 1):
            logger.info(
                'ProalasBoatMessage nav attempt %s/%s: %s',
                attempt,
                _NAV_DETECT_ATTEMPTS,
                _FIRST_NAV_CLICK,
            )
            self.device.click_adb(*_FIRST_NAV_CLICK)
            self.device.sleep(_AFTER_CLICK_DETECT)
            self.device.screenshot()
            if self.appear(RATE_AREA_GET, offset=(20, 20)):
                logger.info('ProalasBoatMessage RateArea_Get matched on attempt %s', attempt)
                self.device.click(RATE_AREA_GET)
                self.device.sleep(_AFTER_RATE_PAGE)
                return True
            logger.warning(
                'ProalasBoatMessage RateArea_Get not found (attempt %s/%s)',
                attempt,
                _NAV_DETECT_ATTEMPTS,
            )
        return False

    def _read_rate_digits(self) -> str:
        engines = (OCR_COLLECTION_RATE_YUV, OCR_COLLECTION_RATE, OCR_COLLECTION_RATE_LO)
        for attempt in range(1, _OCR_RETRY + 1):
            self.device.screenshot()
            for ocr in engines:
                raw = ocr.ocr(self.device.image)
                digits = _normalize_rate_digits(raw)
                logger.info(
                    'ProalasBoatMessage OCR %s try=%s raw=%r digits=%r',
                    ocr.name,
                    attempt,
                    raw,
                    digits,
                )
                if not digits:
                    continue
                if len(digits) >= 3 and set(digits) == {'9'}:
                    continue
                return digits
            if attempt < _OCR_RETRY:
                self.device.sleep(_OCR_RETRY_INTERVAL)
        return ''

    def collect_boat_rate(self, *, boat_max_hint: int | None = None) -> tuple[float, bool]:
        config_name = self._config_name()
        boat_max = int(boat_max_hint) if boat_max_hint and boat_max_hint > 0 else read_boat_max(config_name)

        self.ui_goto_main()
        if not self._open_collection_page():
            logger.warning('ProalasBoatMessage: open collection page failed')
            self.ui_goto_main()
            return 0.0, False

        raw_digits = self._read_rate_digits()
        trimmed = raw_digits[:3] if len(raw_digits) > 3 else raw_digits
        percent, ok = parse_collection_rate_percent(raw_digits, boat_max)

        # PA getBoatMessage：无船坞上限时不采信收藏率
        if boat_max <= 0:
            logger.warning(
                'ProalasBoatMessage: BoatMax=%s，按规则拒绝写入（需先同步 BOAT_MAX）',
                boat_max,
            )
            ok = False

        rate = round(percent / 100.0, 3) if ok else 0.0
        logger.info(
            'ProalasBoatMessage parse raw=%r trimmed=%r boat_max=%s percent=%s rate=%s ok=%s (%.1f%%)',
            raw_digits,
            trimmed,
            boat_max,
            percent,
            rate,
            ok,
            percent,
        )

        if ok:
            logger.attr('BOAT_RATE', rate)
            if write_boat_rate(config_name, rate, config=self.config, boat_max=boat_max):
                logger.info(
                    'ProalasBoatMessage BoatRate=%s (%.1f%%) config=%s',
                    rate,
                    percent,
                    config_name,
                )
            else:
                logger.warning('ProalasBoatMessage ProalasData write failed config=%s', config_name)
        else:
            logger.warning(
                'ProalasBoatMessage: 收藏率未写入 digits=%r trimmed=%r boat_max=%s',
                raw_digits,
                trimmed,
                boat_max,
            )

        self.device.click_adb(*_RETURN_MAIN)
        self.device.sleep(0.5)
        self.ui_goto_main()
        return rate, ok

    def run(self):
        logger.hr('ProalasBoatMessage', level=1)
        self.collect_boat_rate()
        self.config.task_delay(server_update=True)
