# -*- coding: utf-8 -*-
"""编队六槽空位判定：NullBoatIF_add_crop + Otsu agree（主判据 >= 0.88）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from module.logger import logger
from module.proalas import nav_assets as N

Area4 = Tuple[int, int, int, int]
Click = Tuple[int, int]

AGREE_THRESH = 0.88
NCC_THRESH = 0.45
MEAN_AUX_THRESH = 72

_tpl_bgr: Optional[np.ndarray] = None


def _load_template() -> np.ndarray:
    global _tpl_bgr
    if _tpl_bgr is not None:
        return _tpl_bgr
    path = os.path.normpath(N.NULL_BOAT_ADD_CROP)
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f'NullBoatIF_add_crop not found: {path}')
    _tpl_bgr = img
    return _tpl_bgr


def slot_mid_area(slot_rect: Area4, *, keep: float = N.MID_KEEP) -> Area4:
    x1, y1, x2, y2 = slot_rect
    h = y2 - y1
    trim = int(round(h * (1.0 - keep) / 2.0))
    return x1, y1 + trim, x2, y2 - trim


def slot_add_area(slot_rect: Area4) -> Area4:
    mx, my, _, _ = slot_mid_area(slot_rect)
    tx1, ty1, tx2, ty2 = N.ADD_RECT_IN_MID
    return mx + tx1, my + ty1, mx + tx2, my + ty2


def null_slot_metrics(tpl_bgr: np.ndarray, roi_bgr: np.ndarray) -> dict[str, float]:
    h, w = tpl_bgr.shape[:2]
    roi = cv2.resize(roi_bgr, (w, h), interpolation=cv2.INTER_AREA)
    g1 = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    g1n = g1.astype(np.float32) - g1.mean()
    g2n = g2.astype(np.float32) - g2.mean()
    ncc = float((g1n * g2n).sum() / (np.linalg.norm(g1n) * np.linalg.norm(g2n) + 1e-6))
    b1 = cv2.threshold(g1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    b2 = cv2.threshold(g2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    agree = float((b1 == b2).mean())
    return {'agree': agree, 'ncc': ncc, 'mean': float(g2.mean())}


def is_empty_slot(metrics: dict[str, float], *, agree_thresh: float = AGREE_THRESH) -> bool:
    if metrics['agree'] >= agree_thresh:
        return True
    if metrics['ncc'] >= NCC_THRESH and metrics['mean'] < MEAN_AUX_THRESH:
        return True
    return False


@dataclass
class SlotScanResult:
    null_slots: list[int]
    occupied_slots: list[int]
    click_centers: list[tuple[int, Click]]
    metrics_by_slot: dict[int, dict[str, float]]


def scan_team_detail_slots(image) -> SlotScanResult:
    """扫描 TEAM_DETAIL 六槽，返回空槽列表与非空槽点击中心。"""
    tpl = _load_template()
    null_slots: list[int] = []
    occupied: list[int] = []
    centers: list[tuple[int, Click]] = []
    metrics_by_slot: dict[int, dict[str, float]] = {}

    for slot, rect in N.SHIP_SLOT_RECTS.items():
        x1, y1, x2, y2 = slot_add_area(rect)
        roi = image[y1:y2, x1:x2]
        if roi is None or roi.size == 0:
            logger.warning('fleet_null_slot slot=%s empty roi area=(%s,%s,%s,%s)', slot, x1, y1, x2, y2)
            null_slots.append(slot)
            continue
        m = null_slot_metrics(tpl, roi)
        metrics_by_slot[slot] = m
        empty = is_empty_slot(m)
        logger.info(
            'fleet_null_slot slot=%s agree=%.4f ncc=%.4f mean=%.1f empty=%s',
            slot, m['agree'], m['ncc'], m['mean'], empty,
        )
        if empty:
            null_slots.append(slot)
        else:
            occupied.append(slot)
            centers.append((slot, N.SHIP_SLOT_CENTERS[slot]))

    return SlotScanResult(
        null_slots=null_slots,
        occupied_slots=occupied,
        click_centers=centers,
        metrics_by_slot=metrics_by_slot,
    )
