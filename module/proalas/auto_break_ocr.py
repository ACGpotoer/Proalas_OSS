# -*- coding: utf-8 -*-
"""自动突破：在区域内用 cnocr 查找中文并返回点击坐标。"""
from __future__ import annotations

from typing import Optional, Tuple

from module.logger import logger
from module.ocr.ocr import Ocr

Area4 = Tuple[int, int, int, int]
Point = Tuple[int, int]

_OCR_KW = dict(lang='cnocr', letter=(255, 255, 255), threshold=128)


def _row_areas(area: Area4, row_count: int) -> list[Area4]:
    x1, y1, x2, y2 = area
    row_count = max(1, int(row_count))
    total_h = max(1, y2 - y1)
    row_h = total_h // row_count
    rows: list[Area4] = []
    for i in range(row_count):
        ry1 = y1 + i * row_h
        ry2 = y2 if i == row_count - 1 else y1 + (i + 1) * row_h
        rows.append((x1, ry1, x2, ry2))
    return rows


def find_text_click_point(
    image,
    area: Area4,
    text: str,
    *,
    row_count: int = 6,
    name: str = 'AUTO_BREAK_OCR',
) -> Optional[Point]:
    """
    将 area 按行切分，cnocr 识别含 text 的行，返回该行区域中心点（用于 click_adb）。
    """
    target = str(text or '').strip()
    if not target:
        return None
    for idx, row in enumerate(_row_areas(area, row_count)):
        ocr = Ocr([row], name=f'{name}_R{idx}', **_OCR_KW)
        raw = ocr.ocr(image)
        body = str(raw or '').strip()
        if target not in body:
            continue
        x1, y1, x2, y2 = row
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        logger.info('%s 命中 %r row=%s area=%s click=%s', name, target, idx + 1, row, (cx, cy))
        return cx, cy
    return None


def ocr_contains(image, area: Area4, text: str, *, name: str = 'AUTO_BREAK_CHK') -> bool:
    ocr = Ocr([area], name=name, **_OCR_KW)
    raw = str(ocr.ocr(image) or '')
    return str(text) in raw
