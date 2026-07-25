# -*- coding: utf-8 -*-
"""编队页数字 OCR：粗体区用 Digit，细字综合性能放大后 DigitYuv/Digit。"""
from __future__ import annotations

import cv2

from module.base.utils import crop
from module.ocr.ocr import Digit, DigitYuv

_OCR_ALPHABET = '0123456789'


def _valid_int(raw, *, lo: int, hi: int) -> int | None:
    if raw is None:
        return None
    digits = ''.join(c for c in str(raw) if c.isdigit())
    if not digits:
        return None
    try:
        val = int(digits)
    except ValueError:
        return None
    if lo <= val <= hi:
        return val
    return None


def _run_digit(image, area, *, cls, threshold: int, name: str, direct: bool = False):
    ocr = cls([area], threshold=threshold, name=name, letter=(255, 255, 255), alphabet=_OCR_ALPHABET)
    if direct:
        return ocr.ocr([image], direct_ocr=True)
    return ocr.ocr(image)


def ocr_bold_digits(
    image,
    area: tuple[int, int, int, int],
    *,
    name: str = 'FLEET_BOLD_DIGIT',
    lo: int = 100,
    hi: int = 99999,
) -> int | None:
    """Alas 粗体 UI 数字（如编队详情页总战力）。"""
    for cls, th in ((Digit, 128), (Digit, 96), (DigitYuv, 128)):
        raw = _run_digit(image, area, cls=cls, threshold=th, name=name)
        val = _valid_int(raw, lo=lo, hi=hi)
        if val is not None:
            return val
    return None


def ocr_thin_digits(
    image,
    area: tuple[int, int, int, int],
    *,
    name: str = 'FLEET_THIN_DIGIT',
    scale: float = 6.0,
    lo: int = 100,
    hi: int = 9999,
) -> int | None:
    """综合性能等细字：裁剪 → 放大 → 多阈值 DigitYuv/Digit。"""
    roi = crop(image, area)
    if roi is None or roi.size == 0:
        return None
    h, w = roi.shape[:2]
    scaled = cv2.resize(
        roi,
        (max(int(w * scale), 1), max(int(h * scale), 1)),
        interpolation=cv2.INTER_CUBIC,
    )
    fake = (0, 0, scaled.shape[1], scaled.shape[0])
    for cls, th in (
        (DigitYuv, 64),
        (DigitYuv, 96),
        (DigitYuv, 128),
        (Digit, 64),
        (Digit, 96),
        (Digit, 128),
    ):
        raw = _run_digit(scaled, fake, cls=cls, threshold=th, name=name, direct=True)
        val = _valid_int(raw, lo=lo, hi=hi)
        if val is not None:
            return val
    return None
