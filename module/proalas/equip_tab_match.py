# -*- coding: utf-8 -*-
"""单舰详情页左侧 Tab：EquipOcrArea + EquipInput / EquipInputYes 模板导航。"""
from __future__ import annotations

import cv2

from module.base.utils import crop, load_image
from module.logger import logger
from module.proalas import fleet_swap_assets as A


def _area_sim(image, file: str, ref_area: tuple[int, int, int, int], search_area: tuple[int, int, int, int]) -> float:
    tpl = load_image(file, ref_area)
    search = crop(image, search_area, copy=False)
    if tpl.shape != search.shape:
        search = cv2.resize(search, (tpl.shape[1], tpl.shape[0]))
    res = cv2.matchTemplate(tpl, search, cv2.TM_CCOEFF_NORMED)
    return float(res[0, 0]) if res.size == 1 else float(res.max())


def scan_equip_tab_slots(image) -> list[dict]:
    """三处 EquipOcrArea 与 EquipInput 模板相似度。"""
    rows: list[dict] = []
    for slot, area in A.EquipOcrArea.items():
        sim = _area_sim(image, A.EQUIP_INPUT_FILE, A.EQUIP_INPUT_AREA, area)
        rows.append({
            'slot': slot,
            'area': area,
            'center': A.EquipOcrCenter[slot],
            'sim': round(sim, 4),
        })
        logger.info('EquipTab slot=%s area=%s sim=%.4f', slot, area, sim)
    return rows


def pick_equip_tab_slot(image, *, min_sim: float | None = None) -> dict | None:
    rows = scan_equip_tab_slots(image)
    threshold = A._EQUIP_INPUT_SIMILARITY if min_sim is None else min_sim
    best = max(rows, key=lambda r: r['sim'])
    if best['sim'] < threshold:
        logger.warning('EquipTab 无槽位达阈值 %.2f，最高 slot=%s sim=%.4f', threshold, best['slot'], best['sim'])
        return None
    logger.info('EquipTab 命中 slot=%s sim=%.4f center=%s', best['slot'], best['sim'], best['center'])
    return best


def is_equip_tab_selected(image, slot: int) -> bool:
    area = A.EquipOcrArea[slot]
    sim = _area_sim(image, A.EQUIP_INPUT_YES_FILE, A.EQUIP_INPUT_YES_AREA, area)
    selected = sim >= A._EQUIP_INPUT_YES_SIMILARITY
    logger.info('EquipTabYes slot=%s area=%s sim=%.4f selected=%s', slot, area, sim, selected)
    return selected
