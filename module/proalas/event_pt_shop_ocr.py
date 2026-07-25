# -*- coding: utf-8 -*-
"""活动 PT 商店：信物与商品行数字 OCR。"""
from __future__ import annotations

from typing import NamedTuple, Optional

from module.EventPtShop import assets as A
from module.ocr.ocr import Digit, DigitYuv
from module.proalas.fleet_ocr import ocr_thin_digits

_OCR_ALPHABET = '0123456789'


class NumberHit(NamedTuple):
    value: int
    x: int
    y: int
    area: tuple[int, int, int, int]


class ItemPrice(NamedTuple):
    row: int
    slot: int
    value: Optional[int]
    x: int
    y: int
    area: tuple[int, int, int, int]


def _parse_digits(raw) -> Optional[int]:
    if raw is None:
        return None
    digits = ''.join(c for c in str(raw) if c.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def ocr_token_in_area(
    image,
    area: tuple[int, int, int, int],
    *,
    name: str,
    lo: int = 0,
    hi: int = 999999,
    light_background: bool = False,
) -> Optional[int]:
    """信物栏等浅底深字用 gray letter；商品价等深底白字用默认白字 + thin 放大。"""
    if light_background:
        for cls, th, letter in (
            (DigitYuv, 128, (64, 64, 64)),
            (Digit, 96, (128, 128, 128)),
            (Digit, 128, (64, 64, 64)),
            (DigitYuv, 96, (128, 128, 128)),
        ):
            ocr = cls([area], threshold=th, name=name, letter=letter, alphabet=_OCR_ALPHABET)
            val = _parse_digits(ocr.ocr(image))
            if val is not None and lo <= val <= hi:
                return val
        return None

    val = ocr_thin_digits(image, area, name=name, scale=8.0, lo=lo, hi=hi)
    if val is not None:
        return val
    for cls, th in ((DigitYuv, 96), (Digit, 128), (Digit, 96)):
        if cls is DigitYuv:
            ocr = DigitYuv([area], threshold=th, name=name, letter=(255, 255, 255), alphabet=_OCR_ALPHABET)
        else:
            ocr = Digit([area], threshold=th, name=name, letter=(255, 255, 255), alphabet=_OCR_ALPHABET)
        val = _parse_digits(ocr.ocr(image))
        if val is not None and lo <= val <= hi:
            return val
    return None


def read_tokens(image) -> tuple:
    ur = ocr_token_in_area(
        image, A.TOKEN_UR_ITEM_AREA, name='PTSHOP_URITEM', light_background=True,
    )
    pt = ocr_token_in_area(
        image, A.TOKEN_PT_AREA, name='PTSHOP_PT', light_background=True,
    )
    return ur, pt


def scan_row_numbers(
    image,
    area: tuple[int, int, int, int],
    *,
    name: str = 'PTSHOP_ROW',
    window_w: int = 72,
    step: int = 24,
    lo: int = 1,
    hi: int = 999999,
) -> list[NumberHit]:
    """在商品行条带内滑动窗口 OCR，返回数字值与区域中心坐标。"""
    x1, y1, x2, y2 = area
    hits: list[NumberHit] = []
    seen_centers: list[int] = []

    x = x1
    while x < x2:
        wx2 = min(x + window_w, x2)
        if wx2 - x < 12:
            break
        sub = (x, y1, wx2, y2)
        val = ocr_token_in_area(image, sub, name=f'{name}_{x}', lo=lo, hi=hi)
        if val is not None:
            cx = (x + wx2) // 2
            cy = (y1 + y2) // 2
            if not any(abs(cx - px) < 28 for px in seen_centers):
                seen_centers.append(cx)
                hits.append(NumberHit(val, cx, cy, sub))
        x += step

    hits.sort(key=lambda h: h.x)
    return hits


def _area_center(area: tuple[int, int, int, int]) -> tuple[int, int]:
    x1, y1, x2, y2 = area
    return (x1 + x2) // 2, (y1 + y2) // 2


def read_item_prices(image) -> list[ItemPrice]:
    """按固定 5 列子区域读取两行商品价格。"""
    out: list[ItemPrice] = []
    for row_idx, row_areas in enumerate(A.ITEM_PRICE_AREAS, start=1):
        for slot_idx, area in enumerate(row_areas):
            val = ocr_token_in_area(
                image,
                area,
                name=f'PTSHOP_P{row_idx}S{slot_idx + 1}',
                lo=1,
                hi=999999,
            )
            cx, cy = _area_center(area)
            out.append(ItemPrice(row_idx, slot_idx + 1, val, cx, cy, area))
    return out


def scan_item_rows(image) -> dict[str, list[NumberHit]]:
    return {
        'row1': scan_row_numbers(image, A.ITEM_ROW_1_AREA, name='PTSHOP_R1'),
        'row2': scan_row_numbers(image, A.ITEM_ROW_2_AREA, name='PTSHOP_R2'),
    }
