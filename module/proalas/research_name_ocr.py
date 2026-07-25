# -*- coding: utf-8 -*-
"""开发船坞船名 OCR：多 ROI + 放大 + cnocr 多阈值。"""
from __future__ import annotations

import re

import cv2

from module.base.utils import crop
from module.CollectionFill.assets import SHIP_NAME_AREA, SHIP_NAME_AREA_CANDIDATES
from module.logger import logger
from module.ocr.ocr import Ocr

_THRESHOLDS = (128, 96, 160)
_CJK_RE = re.compile(r'[\u4e00-\u9fff]+')
# 空槽英文（底部 EMPTY），不应当作船名
_JUNK = frozenset({'空', '锁定', '未解锁'})


def clean_ship_name(raw: str) -> str:
    text = str(raw or '').strip()
    if not text:
        return ''
    parts = _CJK_RE.findall(text)
    if not parts:
        return ''
    name = max(parts, key=len)
    if len(name) < 2:
        return ''
    if name in _JUNK:
        return ''
    return name


def ocr_research_ship_name(image) -> str:
    """
    Returns:
        清洗后的中文船名；失败返回 ''。
    """
    best = ''
    areas = (SHIP_NAME_AREA,) + tuple(
        a for a in SHIP_NAME_AREA_CANDIDATES if a != SHIP_NAME_AREA
    )
    for area in areas:
        name = _ocr_area(image, area)
        if name and len(name) > len(best):
            best = name
        if len(best) >= 3:
            return best
    return best


def _ocr_area(image, area: tuple[int, int, int, int]) -> str:
    best = ''
    # 原图
    for th in _THRESHOLDS:
        name = _run_cnocr(image, area, th=th, scale=1.0)
        if name:
            if th == 128 and len(name) >= 2:
                return name
            if len(name) > len(best):
                best = name
    # 放大后再试（细字 / 难船名）
    if len(best) < 2:
        for th in _THRESHOLDS:
            name = _run_cnocr(image, area, th=th, scale=2.5)
            if name and len(name) > len(best):
                best = name
                if len(best) >= 3:
                    return best
    return best


def _run_cnocr(image, area, *, th: int, scale: float) -> str:
    try:
        if scale != 1.0:
            roi = crop(image, area)
            if roi is None or getattr(roi, 'size', 0) == 0:
                return ''
            h, w = roi.shape[:2]
            scaled = cv2.resize(
                roi,
                (max(int(w * scale), 1), max(int(h * scale), 1)),
                interpolation=cv2.INTER_CUBIC,
            )
            fake = (0, 0, scaled.shape[1], scaled.shape[0])
            ocr = Ocr(
                [fake],
                lang='cnocr',
                letter=(255, 255, 255),
                threshold=th,
                name=f'RESEARCH_SHIP_NAME_x{scale}_{th}',
            )
            raw = ocr.ocr([scaled], direct_ocr=True)
        else:
            ocr = Ocr(
                [area],
                lang='cnocr',
                letter=(255, 255, 255),
                threshold=th,
                name=f'RESEARCH_SHIP_NAME_{th}',
            )
            raw = ocr.ocr(image)
    except Exception as e:
        logger.warning('Research name OCR failed th=%s scale=%s: %s', th, scale, e)
        return ''
    name = clean_ship_name(str(raw or ''))
    logger.info(
        'Research name OCR area=%s th=%s scale=%s raw=%r -> %r',
        area,
        th,
        scale,
        raw,
        name,
    )
    return name
