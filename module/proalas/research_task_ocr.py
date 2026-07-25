# -*- coding: utf-8 -*-
"""科研任务列表：右侧面板分行 OCR。"""
from __future__ import annotations

from typing import Any

from module.CollectionFill import assets as A
from module.logger import logger
from module.ocr.ocr import Ocr
from module.proalas.fleet_panel_ocr import scan_text_in_area

_OCR_KW = dict(lang='cnocr', letter=(255, 255, 255), threshold=128)


def classify_task_title(text: str) -> str | None:
    """命中关键字 → 规范类型名；无则 None。"""
    body = str(text or '').strip()
    if not body:
        return None
    for key in A.RESEARCH_TASK_KEYWORDS:
        if key in body:
            return key
    return None


def scan_task_titles(image, *, row_count: int = 16, quiet: bool = False) -> list[dict[str, Any]]:
    """
    扫描任务标题行。每项含 text/keyword/click/area/line。
    keyword 为空的行（说明文字）丢弃。
    """
    rows = scan_text_in_area(
        image,
        A.RESEARCH_TASK_LIST_AREA,
        row_count=row_count,
        name='RESEARCH_TASK_LIST',
        quiet=True,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        kw = classify_task_title(str(row.get('text') or ''))
        if not kw:
            continue
        item = dict(row)
        item['keyword'] = kw
        out.append(item)
    if not quiet:
        logger.info('ResearchTaskOCR titles=%s', [(r['keyword'], r['text']) for r in out])
    return out


def count_task_titles(image, *, row_count: int = 16) -> int:
    return len(scan_task_titles(image, row_count=row_count))


def find_keyword_click(image, keyword: str, *, row_count: int = 16):
    """找含 keyword 的第一行中心点。"""
    key = str(keyword or '').strip()
    if not key:
        return None
    for row in scan_task_titles(image, row_count=row_count):
        if row.get('keyword') != key and key not in str(row.get('text') or ''):
            continue
        click = row.get('click')
        if click and len(click) >= 2:
            return int(click[0]), int(click[1])
    return None


def panel_looks_like_list(image, *, min_titles: int = 3) -> bool:
    return count_task_titles(image) >= min_titles


def panel_looks_like_detail(image, *, max_titles: int = 2) -> bool:
    """详情态：标题很少（可配合提交钮再确认）。"""
    return count_task_titles(image) <= max_titles
