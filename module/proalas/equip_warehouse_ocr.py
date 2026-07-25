# -*- coding: utf-8 -*-
"""装备仓库 OCR 解析。"""
from __future__ import annotations

from module.AutoEquip import assets as A
from module.logger import logger


def read_equip_warehouse(image) -> tuple[int, int, int]:
    """
    读取「已用/上限」。

    Returns:
        (current, spare, total) — spare = total - current（空位 / 冗余）
    """
    for ocr in (A.OCR_EQUIP_WAREHOUSE, A.OCR_EQUIP_WAREHOUSE_YUV):
        current, remain, total = ocr.ocr(image)
        if total > 0:
            logger.info(
                'EquipWarehouse OCR %s: %s/%s spare=%s',
                ocr.name,
                current,
                total,
                remain,
            )
            return current, remain, total
    logger.warning('EquipWarehouse OCR failed')
    return 0, 0, 0
