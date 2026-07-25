# -*- coding: utf-8 -*-
"""突破 Tab：TupoInto / TupoIntoYes 在双搜索区分别比对。"""
from __future__ import annotations

import cv2

from module.AutoBreak import assets as A
from module.base.utils import crop, load_image
from module.logger import logger


def _area_sim(
    image,
    file: str,
    ref_area: tuple[int, int, int, int],
    search_area: tuple[int, int, int, int],
) -> float:
    tpl = load_image(file, ref_area)
    search = crop(image, search_area, copy=False)
    if tpl.shape != search.shape:
        search = cv2.resize(search, (tpl.shape[1], tpl.shape[0]))
    res = cv2.matchTemplate(tpl, search, cv2.TM_CCOEFF_NORMED)
    return float(res[0, 0]) if res.size == 1 else float(res.max())


def scan_tupo_into_slots(image) -> list[dict]:
    rows: list[dict] = []
    for slot, area in A.TUPO_TAB_SEARCH_AREAS.items():
        sim = _area_sim(image, A.TUPO_INTO_FILE, A.TUPO_INTO_REF_AREA, area)
        center = A.area_center(area)
        rows.append({
            'slot': slot,
            'area': area,
            'center': center,
            'sim': round(sim, 4),
        })
        logger.info('TupoTab Into slot=%s area=%s sim=%.4f', slot, area, sim)
    return rows


def pick_tupo_into_slot(image, *, min_sim: float | None = None) -> dict | None:
    threshold = A._TUPO_INTO_SIMILARITY if min_sim is None else min_sim
    rows = scan_tupo_into_slots(image)
    hits = [r for r in rows if r['sim'] >= threshold]
    if not hits:
        best = max(rows, key=lambda r: r['sim'])
        logger.warning(
            'TupoTab Into 两区均未达阈值 %.2f，最高 slot=%s sim=%.4f',
            threshold,
            best['slot'],
            best['sim'],
        )
        return None
    picked = max(hits, key=lambda r: r['sim'])
    logger.info(
        'TupoTab Into 命中 slot=%s sim=%.4f center=%s',
        picked['slot'],
        picked['sim'],
        picked['center'],
    )
    return picked


def scan_tupo_into_yes_slots(image) -> list[dict]:
    rows: list[dict] = []
    for slot, area in A.TUPO_TAB_SEARCH_AREAS.items():
        sim = _area_sim(image, A.TUPO_INTO_YES_FILE, A.TUPO_INTO_YES_REF_AREA, area)
        center = A.area_center(area)
        rows.append({
            'slot': slot,
            'area': area,
            'center': center,
            'sim': round(sim, 4),
        })
        logger.info('TupoTab IntoYes slot=%s area=%s sim=%.4f', slot, area, sim)
    return rows


def pick_tupo_into_yes_slot(image, *, min_sim: float | None = None) -> dict | None:
    threshold = A._TUPO_INTO_YES_SIMILARITY if min_sim is None else min_sim
    rows = scan_tupo_into_yes_slots(image)
    hits = [r for r in rows if r['sim'] >= threshold]
    if not hits:
        best = max(rows, key=lambda r: r['sim'])
        logger.warning(
            'TupoTab IntoYes 两区均未达阈值 %.2f，最高 slot=%s sim=%.4f',
            threshold,
            best['slot'],
            best['sim'],
        )
        return None
    picked = max(hits, key=lambda r: r['sim'])
    logger.info(
        'TupoTab IntoYes 命中 slot=%s sim=%.4f area=%s',
        picked['slot'],
        picked['sim'],
        picked['area'],
    )
    return picked
