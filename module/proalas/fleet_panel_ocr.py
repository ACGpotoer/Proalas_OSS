# -*- coding: utf-8 -*-
"""
编队/船坞左侧面板 OCR：在固定区域内用原生 Alas cnocr 分行识别，记录文字与点击坐标。

默认区域 (150, 300, 350, 630) — 1280×720 左栏约 x∈[150,350]、y∈[300,630]。
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from module.logger import logger
from module.ocr.ocr import Ocr

Area4 = Tuple[int, int, int, int]
Point = Tuple[int, int]

# 用户指定：当前页面左栏文字区
FLEET_LEFT_PANEL_AREA: Area4 = (150, 300, 350, 630)

_OCR_KW = dict(lang='cnocr', letter=(255, 255, 255), threshold=128)
_OCR_NAME = 'FLEET_LEFT_PANEL'


def _row_areas(area: Area4, row_count: int) -> List[Area4]:
    x1, y1, x2, y2 = area
    row_count = max(1, int(row_count))
    total_h = max(1, y2 - y1)
    row_h = total_h // row_count
    rows: List[Area4] = []
    for i in range(row_count):
        ry1 = y1 + i * row_h
        ry2 = y2 if i == row_count - 1 else y1 + (i + 1) * row_h
        rows.append((x1, ry1, x2, ry2))
    return rows


def _default_row_count(area: Area4, *, min_row_h: int = 48, max_rows: int = 12) -> int:
    _, y1, _, y2 = area
    h = max(1, y2 - y1)
    return max(1, min(max_rows, h // max(1, min_row_h)))


def scan_text_in_area(
    image,
    area: Area4 = FLEET_LEFT_PANEL_AREA,
    *,
    row_count: Optional[int] = None,
    name: str = _OCR_NAME,
    quiet: bool = False,
) -> List[dict[str, Any]]:
    """
    将 area 按行切分，每行用 Alas Ocr(cnocr) 识别，返回文字与屏幕坐标。

    每项:
      text: 识别文本
      area: [x1,y1,x2,y2] 屏幕区域
      click: [cx,cy] 行区域中心（建议点击点）
      line: 行号（从 1 起）
    """
    n_rows = row_count if row_count is not None else _default_row_count(area)
    out: List[dict[str, Any]] = []

    for idx, row in enumerate(_row_areas(area, n_rows), start=1):
        ocr = Ocr([row], name=f'{name}_R{idx}', **_OCR_KW)
        raw = str(ocr.ocr(image) or '').strip()
        if not raw:
            continue
        x1, y1, x2, y2 = row
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        item = {
            'text': raw,
            'area': [x1, y1, x2, y2],
            'click': [cx, cy],
            'line': idx,
        }
        out.append(item)
        if not quiet:
            logger.info('%s line=%s text=%r click=%s area=%s', name, idx, raw, (cx, cy), item['area'])

    if not quiet:
        logger.info('%s 共识别 %s 条（扫描 %s 行）area=%s', name, len(out), n_rows, area)
    return out


def find_text_click(
    image,
    text: str,
    *,
    area: Area4 = FLEET_LEFT_PANEL_AREA,
    row_count: Optional[int] = None,
    contains: bool = True,
) -> Optional[Point]:
    """在扫描结果中查找含 text 的行，返回点击坐标。"""
    target = str(text or '').strip()
    if not target:
        return None
    for row in scan_text_in_area(image, area, row_count=row_count):
        body = row.get('text', '')
        matched = (target in body) if contains else (body == target)
        if not matched:
            continue
        cx, cy = row['click']
        return int(cx), int(cy)
    return None


def format_scan_lines(rows: List[dict[str, Any]]) -> str:
    lines = []
    for row in rows:
        lines.append(
            f"L{row.get('line')}: {row.get('text')!r} @ click={tuple(row.get('click', []))}"
        )
    return '\n'.join(lines)
