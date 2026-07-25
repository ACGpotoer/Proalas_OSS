# -*- coding: utf-8 -*-
"""单舰页 → 装备五槽：模板点 Tab + EquipInputYes 验页。"""
from __future__ import annotations

from module.AutoEquip import assets as EA
from module.FleetStrength import assets as FA
from module.logger import logger
from module.proalas.equip_tab_match import is_equip_tab_selected, pick_equip_tab_slot

_MAX_TAB_ATTEMPTS = 3
CLICK_BACK_DETAIL = FA.CLICK_RETURN_DETAIL  # (50, 50)


def open_equip_five_slot_panel(ui) -> int | None:
    """
    在单舰详情页：
      1. 扫描 EquipOcrArea（左侧 3 个 Tab 位），找「装备」Tab
      2. EquipInputYes 未命中则再点
      3. 返回命中的 Tab 槽位号（供后续 EquipInputYes 验五槽页）
    """
    for attempt in range(1, _MAX_TAB_ATTEMPTS + 1):
        ui.device.screenshot()
        picked = pick_equip_tab_slot(ui.device.image)
        if not picked:
            logger.error('EquipTab 未识别装备 Tab attempt=%s', attempt)
            return None

        slot = int(picked['slot'])
        center = tuple(picked['center'])
        logger.info('EquipTab 点击装备 Tab slot=%s %s attempt=%s', slot, center, attempt)
        ui.device.click_adb(*center)
        ui.device.sleep(max(EA.WAIT_AFTER_TAB, EA.MIN_CLICK_INTERVAL))
        ui.device.screenshot()

        if is_equip_tab_selected(ui.device.image, slot):
            logger.info('EquipTab 已进入装备五槽页 tab_slot=%s', slot)
            return slot

        logger.warning('EquipTab 未选中，重试点击 slot=%s', slot)

    logger.error('EquipTab 打开装备五槽失败')
    return None


def confirm_on_five_slot_panel(ui, tab_slot: int, *, after_click_back: bool = True) -> bool:
    """
    校验是否在五装备槽界面：可选先点 (50,50)，再比 EquipInputYes。
    """
    if after_click_back:
        logger.info('EquipTab 验五槽：点返回 %s', CLICK_BACK_DETAIL)
        ui.device.click_adb(*CLICK_BACK_DETAIL)
        ui.device.sleep(max(EA.WAIT_AFTER_TAB, EA.MIN_CLICK_INTERVAL))
    ui.device.screenshot()
    ok = is_equip_tab_selected(ui.device.image, tab_slot)
    logger.info('EquipTab 五槽页 EquipInputYes tab_slot=%s ok=%s', tab_slot, ok)
    return ok
