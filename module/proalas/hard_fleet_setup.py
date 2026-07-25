# -*- coding: utf-8 -*-
"""
困难活动图首次编队：清空 → 确认弹窗 → 点推荐（固定坐标）。

复用原版 FleetOperator.clear() / is_hard_satisfied()；推荐按钮使用实测坐标死点。
"""
from __future__ import annotations

from module.base.timer import Timer
from module.logger import logger

# 困难图推荐按钮坐标（cn 1280x720）
HARD_FLEET_ADVICE_COORDS = (
    (1050, 220),  # 一队
    (1050, 330),  # 二队
    (1050, 470),  # 潜艇
)


def proalas_auto_hard_fleet_enabled(config) -> bool:
    return bool(getattr(config, 'ProalasEventFormatFix_AutoHardFleet', True))


def _map_assets():
    from module.map.assets import (
        FLEET_1_ADVICE,
        FLEET_1_BAR,
        FLEET_1_CHOOSE,
        FLEET_1_CLEAR,
        FLEET_1_HARD_SATIESFIED,
        FLEET_1_IN_USE,
        FLEET_2_ADVICE,
        FLEET_2_BAR,
        FLEET_2_CHOOSE,
        FLEET_2_CLEAR,
        FLEET_2_HARD_SATIESFIED,
        FLEET_2_IN_USE,
        FLEET_2_IN_USE_W15,
        FLEET_PREPARATION,
        MAP_PREPARATION,
        SUBMARINE_ADVICE,
        SUBMARINE_BAR,
        SUBMARINE_CHOOSE,
        SUBMARINE_CLEAR,
        SUBMARINE_HARD_SATIESFIED,
        SUBMARINE_IN_USE,
    )

    return locals()


def build_fleet_operators(main):
    from module.map.map_fleet_preparation import FleetOperator

    assets = _map_assets()
    fleet_1 = FleetOperator(
        choose=assets['FLEET_1_CHOOSE'],
        advice=assets['FLEET_1_ADVICE'],
        bar=assets['FLEET_1_BAR'],
        clear=assets['FLEET_1_CLEAR'],
        in_use=assets['FLEET_1_IN_USE'],
        hard_satisfied=assets['FLEET_1_HARD_SATIESFIED'],
        main=main,
    )
    y = assets['FLEET_1_CLEAR'].button[1] - assets['FLEET_1_CLEAR'].area[1]
    fleet_2_in_use = assets['FLEET_2_IN_USE_W15'] if y < -10 else assets['FLEET_2_IN_USE']
    fleet_2 = FleetOperator(
        choose=assets['FLEET_2_CHOOSE'],
        advice=assets['FLEET_2_ADVICE'],
        bar=assets['FLEET_2_BAR'],
        clear=assets['FLEET_2_CLEAR'],
        in_use=fleet_2_in_use,
        hard_satisfied=assets['FLEET_2_HARD_SATIESFIED'],
        main=main,
    )
    submarine = FleetOperator(
        choose=assets['SUBMARINE_CHOOSE'],
        advice=assets['SUBMARINE_ADVICE'],
        bar=assets['SUBMARINE_BAR'],
        clear=assets['SUBMARINE_CLEAR'],
        in_use=assets['SUBMARINE_IN_USE'],
        hard_satisfied=assets['SUBMARINE_HARD_SATIESFIED'],
        main=main,
    )
    return fleet_1, fleet_2, submarine


def hard_fleet_needs_setup(main, fleet_1, fleet_2, submarine) -> bool:
    if main.config.Fleet_Fleet1 and fleet_1.is_hard() and fleet_1.is_hard_satisfied() is False:
        return True
    if main.config.Fleet_Fleet2 and fleet_2.is_hard() and fleet_2.is_hard_satisfied() is False:
        return True
    if main.config.Submarine_Fleet and submarine.allow() and submarine.is_hard() and submarine.is_hard_satisfied() is False:
        return True
    return False


def recommend_advice(operator, coord: tuple[int, int], *, timeout: int = 20) -> bool:
    """清空后点击推荐坐标，直到满足困难限制或超时。"""
    main = operator.main
    click_timer = Timer(3, count=6)
    limit = Timer(timeout, count=timeout * 2).start()
    skip_first = True
    while not limit.reached():
        if skip_first:
            skip_first = False
        else:
            main.device.screenshot()

        if operator.is_hard_satisfied():
            return True

        if click_timer.reached():
            main.device.click(coord)
            click_timer.reset()

    return bool(operator.is_hard_satisfied())


def setup_hard_fleet_slot(operator, coord: tuple[int, int]) -> bool:
    if not operator.is_hard():
        return False
    if operator.is_hard_satisfied():
        return False

    logger.info('Hard fleet setup: %s clear → recommend', operator)
    operator.clear()
    if operator.is_hard_satisfied():
        return True
    if recommend_advice(operator, coord):
        return True

    logger.warning('Hard fleet setup failed: %s', operator)
    return False


def setup_hard_fleet_on_preparation(main) -> bool:
    """在 FLEET_PREPARATION 界面为未满足的困难槽位配队。"""
    assets = _map_assets()
    fleet_preparation = assets['FLEET_PREPARATION']
    if not main.appear(fleet_preparation, offset=(20, 50)):
        logger.warning('Hard fleet setup: not on FLEET_PREPARATION')
        return False

    fleet_1, fleet_2, submarine = build_fleet_operators(main)
    if not hard_fleet_needs_setup(main, fleet_1, fleet_2, submarine):
        return False

    changed = False
    slots = [
        (bool(main.config.Fleet_Fleet1), fleet_1, HARD_FLEET_ADVICE_COORDS[0]),
        (bool(main.config.Fleet_Fleet2), fleet_2, HARD_FLEET_ADVICE_COORDS[1]),
        (bool(main.config.Submarine_Fleet and submarine.allow()), submarine, HARD_FLEET_ADVICE_COORDS[2]),
    ]
    for enabled, operator, coord in slots:
        if not enabled:
            continue
        if setup_hard_fleet_slot(operator, coord):
            changed = True

    h1, h2, h3 = fleet_1.is_hard_satisfied(), fleet_2.is_hard_satisfied(), submarine.is_hard_satisfied()
    logger.info('Hard fleet setup result: Fleet_1=%s Fleet_2=%s Submarine=%s changed=%s', h1, h2, h3, changed)
    return changed


def try_setup_hard_fleet(main) -> bool:
    """ProAlas：困难图自动配队入口（须在选队页）。"""
    if not proalas_auto_hard_fleet_enabled(main.config):
        return False
    return setup_hard_fleet_on_preparation(main)


def navigate_to_fleet_preparation(campaign_run, event_folder: str, stage: str = 'ht1', *, mode: str = 'hard') -> bool:
    """进入活动困难关选队界面（MAP_PREPARATION → FLEET_PREPARATION）。"""
    from module.ui.assets import BACK_ARROW, DAILY_CHECK

    assets = _map_assets()
    fleet_preparation = assets['FLEET_PREPARATION']
    map_preparation = assets['MAP_PREPARATION']

    campaign_run.config.override(Campaign_Event=event_folder)
    campaign_run.load_campaign(stage, folder=event_folder)
    campaign = campaign_run.campaign

    campaign.device.stuck_record_clear()
    campaign.device.click_record_clear()
    campaign.ui_goto_main()
    campaign.ensure_campaign_ui(name=stage, mode=mode)

    try:
        entrance = campaign.campaign_get_entrance(stage)
    except Exception as exc:
        logger.error('Hard fleet navigate: entrance missing %s (%s)', stage, exc)
        return False

    timeout = Timer(60, count=120).start()
    entrance_click = 0
    map_click = 0
    while not timeout.reached():
        campaign.device.screenshot()

        if campaign.appear(DAILY_CHECK, offset=(20, 20), interval=3):
            campaign.device.click(BACK_ARROW)
            continue
        if campaign.handle_story_skip():
            continue
        if campaign.appear(fleet_preparation, offset=(20, 50)):
            logger.info('Hard fleet navigate: on FLEET_PREPARATION (%s)', stage)
            return True
        if map_click < 8 and campaign.handle_map_mode_switch(mode) and campaign.handle_map_preparation():
            campaign.map_get_info()
            campaign.device.click(map_preparation)
            map_click += 1
            continue
        if campaign.appear_then_click(entrance, interval=2):
            entrance_click += 1
            if entrance_click > 12:
                logger.error('Hard fleet navigate: too many entrance clicks %s', stage)
                return False
            continue

    logger.error('Hard fleet navigate: timeout %s', stage)
    return False


def run_proactive_hard_fleet_setup(campaign_run, event_folder: str, stage: str = 'ht1') -> bool:
    """主动进入 ht 关完成困难编队后退回章节选关。"""
    if not proalas_auto_hard_fleet_enabled(campaign_run.config):
        return False
    if not navigate_to_fleet_preparation(campaign_run, event_folder, stage=stage):
        return False

    ok = setup_hard_fleet_on_preparation(campaign_run.campaign)
    campaign_run.campaign.enter_map_cancel()
    return ok
