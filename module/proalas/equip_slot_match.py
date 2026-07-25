# -*- coding: utf-8 -*-
"""
空装备槽检测：中心白色「+」特征（非整图模板）。

空槽共性：80×80 区域中心有白色十字；前排/后排背景不同，整图 TM/SSIM 会误判。
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from module.AutoEquip import assets as A
from module.base.utils import crop, extract_letters
from module.logger import logger

# 中心 48×48 白字二值图 TM（slot2 空槽实测约 0.50）
CENTER_PLUS_TM_MIN = 0.48
# 十字臂在白字图上的平均亮度比（0~1）
CROSS_ARM_MIN = 0.35
CENTER_PLUS_SIZE = 48
CROSS_ARM_HALF = 2


def _asset_path(name: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(root, 'assets', 'cn', 'AutoEquip', name)


def _template_path() -> str:
    return _asset_path('NullEquipment.png')


def _null_any_template_path() -> str:
    return _asset_path('NullAnyEquipment.png')


def _white_binary(image) -> np.ndarray:
    return extract_letters(image, letter=(255, 255, 255), threshold=128)


def _center_crop(image, size: int = CENTER_PLUS_SIZE) -> np.ndarray:
    h, w = image.shape[:2]
    cx, cy = w // 2, h // 2
    half = size // 2
    return image[cy - half:cy + half, cx - half:cx + half]


def _load_center_plus_template() -> np.ndarray:
    tpl = cv2.imread(_template_path())
    if tpl is None:
        raise FileNotFoundError(f'NullEquipment template missing: {_template_path()}')
    return _center_crop(_white_binary(tpl), CENTER_PLUS_SIZE)


def _cross_arm_scores(binary_center: np.ndarray) -> tuple[float, float]:
    h, w = binary_center.shape[:2]
    cx, cy = w // 2, h // 2
    arm = CROSS_ARM_HALF
    h_arm = float(binary_center[cy - arm:cy + arm + 1, :].mean()) / 255.0
    v_arm = float(binary_center[:, cx - arm:cx + arm + 1].mean()) / 255.0
    return h_arm, v_arm


def detect_empty_equip_slot(region_bgr) -> dict:
    """
    在 80×80 槽位图上检测是否为空槽（中心白十字）。

    Returns:
        is_null, center_tm, h_arm, v_arm, method
    """
    binary = _white_binary(region_bgr)
    center_bin = _center_crop(binary, CENTER_PLUS_SIZE)
    plus_tpl = _load_center_plus_template()

    if center_bin.shape != plus_tpl.shape:
        center_bin = cv2.resize(center_bin, (plus_tpl.shape[1], plus_tpl.shape[0]))

    center_tm = float(cv2.matchTemplate(center_bin, plus_tpl, cv2.TM_CCOEFF_NORMED)[0][0])
    h_arm, v_arm = _cross_arm_scores(center_bin)
    has_cross = h_arm >= CROSS_ARM_MIN and v_arm >= CROSS_ARM_MIN
    is_null = has_cross and center_tm >= CENTER_PLUS_TM_MIN

    return {
        'center_tm': round(center_tm, 4),
        'h_arm': round(h_arm, 4),
        'v_arm': round(v_arm, 4),
        'has_cross': has_cross,
        'is_null': is_null,
        'method': 'white_cross_center',
    }


def slot_area(center: tuple[int, int], *, radius: int = A.EQUIP_SLOT_RADIUS) -> tuple[int, int, int, int]:
    cx, cy = center
    return cx - radius, cy - radius, cx + radius, cy + radius


def match_null_equipment(image, center: tuple[int, int]) -> dict:
    area = slot_area(center)
    region = crop(image, area)
    det = detect_empty_equip_slot(region)
    return {
        'center': center,
        'area': area,
        **det,
    }


def detect_no_replaceable_equipment(image) -> dict:
    """
    检测装备更换面板上是否出现「没有可替换的装备」空列表条带。

    模板：NullAnyEquipment，区域 (280,90)-(1180,240)。
    """
    tpl = cv2.imread(_null_any_template_path())
    if tpl is None:
        raise FileNotFoundError(f'NullAnyEquipment template missing: {_null_any_template_path()}')

    area = A.NULL_ANY_EQUIPMENT_AREA
    region = crop(image, area)
    if region.shape[:2] != tpl.shape[:2]:
        region = cv2.resize(region, (tpl.shape[1], tpl.shape[0]))

    tm = float(cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)[0][0])
    is_empty_list = tm >= A.NULL_ANY_EQUIPMENT_TM_MIN
    logger.info(
        'NullAnyEquipment area=%s TM=%.4f => %s',
        area,
        tm,
        'no_replaceable' if is_empty_list else 'has_candidates',
    )
    return {
        'area': area,
        'tm': round(tm, 4),
        'is_no_replaceable': is_empty_list,
        'method': 'null_any_equipment_banner',
    }


def scan_all_equip_slots(image) -> list[dict]:
    out: list[dict] = []
    for slot_id, center in enumerate(A.EQUIP_SLOT_CENTERS, start=1):
        row = match_null_equipment(image, center)
        row['slot'] = slot_id
        logger.info(
            'EquipSlot slot%s center=%s cross=%s TM=%.4f h=%.3f v=%.3f => %s',
            slot_id,
            center,
            row['has_cross'],
            row['center_tm'],
            row['h_arm'],
            row['v_arm'],
            'empty' if row['is_null'] else 'equipped',
        )
        out.append(row)
    return out
