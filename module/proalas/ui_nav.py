# -*- coding: utf-8 -*-
"""编队采集导航：跨页 appear + 页内坐标（切队保留 FleetStrength 六队死坐标）。"""
from __future__ import annotations

from module.FleetStrength import assets as A
from module.logger import logger
from module.proalas import nav_assets as N


class FleetUiNav:
    """ProalasFleetStrength 用；ui 为 UI 子类实例。"""

    def __init__(self, ui) -> None:
        self.ui = ui

    @property
    def device(self):
        return self.ui.device

    def _tap(self, xy: tuple[int, int], *, delay: float | None = None) -> None:
        d = A._AFTER_CLICK if delay is None else delay
        self.device.click_adb(*xy)
        self.device.sleep(max(float(d), A.MIN_CLICK_INTERVAL))

    def _appear(self, button) -> bool:
        self.device.screenshot()
        return self.ui.appear(
            button,
            offset=N.TEMPLATE_OFFSET,
            similarity=N.TEMPLATE_SIMILARITY,
        )

    def _on_team_detail(self) -> bool:
        return self._appear(N.BianDui)

    def _on_formation_list(self) -> bool:
        return self._appear(N.FleetSituationIn)

    def goto_main(self) -> None:
        self.ui.ui_goto_main()

    def goto_formation_list(self) -> bool:
        """MAIN → FORMATION_LIST。"""
        self.goto_main()
        logger.info('ui_nav click formation %s', A.CLICK_FORMATION)
        self._tap(A.CLICK_FORMATION, delay=A._AFTER_CLICK)
        self.device.screenshot()
        if not self._on_formation_list():
            logger.error('ui_nav FleetSituationIn 未匹配，未进入编队列表')
            return False
        logger.info('ui_nav state=FORMATION_LIST')
        return True

    def switch_team_on_list(self, team_no: int) -> None:
        """编队列表页切队（尚无 BianDui，沿用原版两步死坐标）。"""
        idx = team_no - 1
        if not 0 <= idx < len(A.TEAM_SWITCH_CLICKS):
            logger.warning('ui_nav invalid team_no=%s on list', team_no)
            return
        for i, pos in enumerate(A.TEAM_SWITCH_CLICKS[idx], 1):
            logger.info('ui_nav list team=%s switch %s/2 %s', team_no, i, pos)
            self._tap(pos, delay=A._AFTER_SWITCH)

    def goto_team_detail(self) -> bool:
        """FORMATION_LIST → TEAM_DETAIL（FleetSituationIn 中心，非旧 CLICK_DETAILS）。"""
        if not self._on_formation_list():
            logger.error('ui_nav goto_team_detail: 不在 FORMATION_LIST')
            return False
        logger.info('ui_nav click FleetSituationIn center %s', N.FLEET_SITUATION_IN_CENTER)
        self._tap(N.FLEET_SITUATION_IN_CENTER, delay=A._AFTER_DETAILS)
        if not self._on_team_detail():
            logger.error('ui_nav BianDui 未匹配，未进入六槽详情')
            return False
        logger.info('ui_nav state=TEAM_DETAIL')
        return True

    def switch_team_on_detail(self, team_no: int) -> bool:
        """TEAM_DETAIL 内切队；必须先 appear BianDui。"""
        if not self._on_team_detail():
            logger.error('ui_nav switch_team_on_detail: BianDui 未匹配，禁止切队')
            return False
        idx = team_no - 1
        if not 0 <= idx < len(A.TEAM_SWITCH_CLICKS):
            logger.warning('ui_nav invalid team_no=%s on detail', team_no)
            return False
        for i, pos in enumerate(A.TEAM_SWITCH_CLICKS[idx], 1):
            logger.info('ui_nav detail team=%s switch %s/2 %s', team_no, i, pos)
            self._tap(pos, delay=A._AFTER_SWITCH)
        self.device.screenshot()
        if not self._on_team_detail():
            logger.error('ui_nav 切队后 BianDui 丢失 team=%s', team_no)
            return False
        return True

    def open_ship_detail(self, click_xy: tuple[int, int]) -> bool:
        """
        点击非空槽进入单舰页。
        BianDui 不可见表示已进入 SHIP_DETAIL（语义与常规 appear 相反）。
        """
        for attempt in range(1, N.MAX_OPEN_SHIP_RETRIES + 1):
            logger.info('ui_nav open ship attempt=%s click %s', attempt, click_xy)
            self._tap(click_xy, delay=A._AFTER_SHIP)
            self.device.screenshot()
            if not self._on_team_detail():
                logger.info('ui_nav state=SHIP_DETAIL (BianDui absent)')
                return True
            logger.warning('ui_nav 仍在 TEAM_DETAIL，重试点击槽位 %s/%s', attempt, N.MAX_OPEN_SHIP_RETRIES)
        logger.error('ui_nav 进单舰失败 click=%s', click_xy)
        return False

    def return_to_team_detail(self) -> bool:
        """SHIP_DETAIL → TEAM_DETAIL；误退列表则 FleetSituationIn 重进。"""
        logger.info('ui_nav return detail %s', A.CLICK_RETURN_DETAIL)
        self._tap(A.CLICK_RETURN_DETAIL, delay=A._AFTER_RETURN_DETAIL)
        self.device.screenshot()
        if self._on_team_detail():
            logger.info('ui_nav back to TEAM_DETAIL')
            return True
        if self._on_formation_list():
            logger.warning('ui_nav 误退 FORMATION_LIST，重进详情')
            return self.goto_team_detail()
        logger.error('ui_nav return_to_team_detail: 未知页面')
        return False

    def abort_to_main(self, reason: str) -> None:
        logger.error('ui_nav abort: %s', reason)
        self.goto_main()
