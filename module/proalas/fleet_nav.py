# -*- coding: utf-8 -*-
"""编队界面导航（与 ProalasFleetStrength 坐标一致）。"""
from __future__ import annotations

from module.FleetStrength import assets as FA
from module.logger import logger


def _tap(ui, xy: tuple[int, int], *, delay: float | None = None) -> None:
    d = FA._AFTER_CLICK if delay is None else delay
    ui.device.click_adb(*xy)
    ui.device.sleep(max(float(d), FA.MIN_CLICK_INTERVAL))


def switch_team(ui, team_no: int) -> None:
    idx = team_no - 1
    if not 0 <= idx < len(FA.TEAM_SWITCH_CLICKS):
        logger.warning('fleet_nav invalid team_no=%s', team_no)
        return
    for i, pos in enumerate(FA.TEAM_SWITCH_CLICKS[idx], 1):
        logger.info('fleet_nav team=%s switch %s/%s %s', team_no, i, 2, pos)
        _tap(ui, pos, delay=FA._AFTER_SWITCH)


def open_team_details(ui, team_no: int) -> None:
    """主界面 → 编队 → 指定队 → 详情页（六舰概览）。"""
    ui.ui_goto_main()
    logger.info('fleet_nav formation %s', FA.CLICK_FORMATION)
    _tap(ui, FA.CLICK_FORMATION)
    switch_team(ui, team_no)
    logger.info('fleet_nav details %s', FA.CLICK_DETAILS)
    _tap(ui, FA.CLICK_DETAILS, delay=FA._AFTER_DETAILS)


def open_ship_detail(ui, ship_slot: int) -> None:
    """详情页 → 单舰战力界面。ship_slot 1–6。"""
    if not 1 <= ship_slot <= len(FA.SHIP_CLICKS):
        return
    pos = FA.SHIP_CLICKS[ship_slot - 1]
    logger.info('fleet_nav open ship slot=%s %s', ship_slot, pos)
    _tap(ui, pos, delay=FA._AFTER_SHIP)
    ui.device.screenshot()


def return_to_fleet_detail(ui, *, back_xy: tuple[int, int] | None = None) -> None:
    pos = back_xy if back_xy is not None else FA.CLICK_RETURN_DETAIL
    logger.info('fleet_nav return detail %s', pos)
    _tap(ui, pos, delay=FA._AFTER_RETURN_DETAIL)
    ui.device.screenshot()


def return_to_main(ui) -> None:
    logger.info('fleet_nav return main %s', FA.CLICK_RETURN_MAIN)
    _tap(ui, FA.CLICK_RETURN_MAIN)
    ui.ui_goto_main()
