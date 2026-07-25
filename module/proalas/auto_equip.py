# -*- coding: utf-8 -*-
"""
ProAlas 自动换装备和配置装备。

主流程：按指定编队（默认第 3 队）逐舰进入战力页 → 装备五槽 → 空槽补齐。
可与 ProalasAutoFleetChange 联动，共用 TeamNo。
"""
from __future__ import annotations

from module.AutoEquip import assets as A
from module.logger import logger
from module.proalas.equip_tab_match import is_equip_tab_selected
from module.proalas.equip_tab_nav import CLICK_BACK_DETAIL, confirm_on_five_slot_panel, open_equip_five_slot_panel
from module.proalas.ui_nav import FleetUiNav
from module.proalas.auto_equip_config import (
    parse_allow_craft,
    parse_craft_coin_limit,
    parse_equip_quality,
    parse_replace_surplus_purple,
    parse_team_no,
    parse_warehouse_reserve,
)
from module.proalas.equip_slot_match import (
    detect_no_replaceable_equipment,
    scan_all_equip_slots,
)
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas import fleet_nav
from module.proalas_collector.userdata import read_game_resource, write_auto_equip_result
from module.ui.ui import UI

SHIP_COUNT = 6
_MAX_SLOT_ROUNDS = 10


def fill_team_equipment(ui: UI, team_no: int) -> dict:
    """供 ProalasAutoFleetChange 等任务调用的按队补齐装备入口。"""
    task = ProalasAutoEquip(config=ui.config, device=ui.device)
    return task._fill_team_equipment(team_no)


class ProalasAutoEquip(UI):
    equipped_count: int = 0
    replaced_purple_count: int = 0
    crafted_count: int = 0
    slots_no_replaceable: int = 0
    ships_processed: int = 0
    _equip_tab_slot: int | None = None

    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _tap(
        self,
        xy: tuple[int, int],
        *,
        delay: float = A.AFTER_CLICK,
        prev: tuple[int, int] | None = None,
    ) -> None:
        if prev is not None and prev == xy:
            logger.info('AutoEquip 连续同坐标 %s，额外等待 %ss', xy, A.SAME_POS_EXTRA_DELAY)
            self.device.sleep(A.SAME_POS_EXTRA_DELAY)
        self.device.click_adb(*xy)
        self.device.sleep(max(float(delay), A.MIN_CLICK_INTERVAL))

    def _return_to_five_slots_after_slot(self) -> bool:
        """单装备槽处理完：点 (50,50) 一次，EquipInputYes 命中则仍在五槽页。"""
        if self._equip_tab_slot is None:
            logger.warning('AutoEquip: 无 tab_slot，跳过 EquipInputYes 验页')
            self.device.screenshot()
            return False
        return confirm_on_five_slot_panel(self, self._equip_tab_slot, after_click_back=True)

    def _open_ship_equip_panel(self) -> bool:
        """单舰详情页 → 模板识别装备 Tab → 五槽界面。"""
        tab_slot = open_equip_five_slot_panel(self)
        if tab_slot is None:
            return False
        self._equip_tab_slot = tab_slot
        return True

    def _fill_one_empty_slot(self, center: tuple[int, int], slot_id: int) -> str:
        """
        点击空槽 → 筛选 → 判断是否有可替换装备 → 装配或返回五槽。

        Returns:
            filled | no_replaceable | failed
        """
        logger.info('AutoEquip: 空槽 slot=%s center=%s', slot_id, center)
        self._tap(center, delay=A.WAIT_AFTER_SLOT)
        self.device.screenshot()

        logger.info('AutoEquip: 打开装备筛选 %s', A.CLICK_OPEN_EQUIP_LIST_FILTER)
        self._tap(A.CLICK_OPEN_EQUIP_LIST_FILTER, delay=A.WAIT_AFTER_FILTER)
        self.device.screenshot()

        banner = detect_no_replaceable_equipment(self.device.image)
        if banner['is_no_replaceable']:
            logger.info('AutoEquip: slot=%s 无可替换装备', slot_id)
            self._return_to_five_slots_after_slot()
            return 'no_replaceable'

        logger.info('AutoEquip: slot=%s 选中候选 %s', slot_id, A.CLICK_PICK_CANDIDATE_EQUIP)
        self._tap(A.CLICK_PICK_CANDIDATE_EQUIP, delay=A.WAIT_AFTER_PICK)
        logger.info('AutoEquip: slot=%s 确认装配 %s', slot_id, A.CLICK_CONFIRM_EQUIP_AND_BACK)
        self._tap(A.CLICK_CONFIRM_EQUIP_AND_BACK, delay=A.WAIT_AFTER_TAB)
        self.device.sleep(A.WAIT_AFTER_EQUIP_SUCCESS)
        self._return_to_five_slots_after_slot()
        return 'filled'

    def _fill_empty_slots_on_current_ship(self) -> dict[str, int]:
        stats = {'filled': 0, 'no_replaceable': 0, 'equip_panel': 0}
        self._equip_tab_slot = None
        if not self._open_ship_equip_panel():
            return stats
        stats['equip_panel'] = 1

        processed: set[int] = set()
        for round_no in range(1, _MAX_SLOT_ROUNDS + 1):
            self.device.screenshot()
            slots = scan_all_equip_slots(self.device.image)
            empty_slots = [row for row in slots if row['is_null']]
            logger.info(
                'AutoEquip: 五装备槽扫描 round=%s empty=%s / 5 已处理=%s',
                round_no,
                [r['slot'] for r in empty_slots],
                sorted(processed),
            )
            pending = [
                row for row in empty_slots
                if row['slot'] not in processed
            ]
            if not pending:
                break
            row = pending[0]
            result = self._fill_one_empty_slot(row['center'], row['slot'])
            processed.add(row['slot'])
            if result == 'filled':
                stats['filled'] += 1
            elif result == 'no_replaceable':
                stats['no_replaceable'] += 1

        return stats

    def return_to_team_detail_after_ship(self) -> None:
        """离舰：仅在非五槽页时点返回，直到回到六舰详情。"""
        nav = FleetUiNav(self)
        tab = self._equip_tab_slot or 3
        for attempt in range(1, 5):
            self.device.screenshot()
            if nav._on_team_detail():
                logger.info('AutoEquip: 已在六舰详情 attempt=%s', attempt)
                return
            if is_equip_tab_selected(self.device.image, tab):
                logger.info('AutoEquip: 仍在五槽页，点 %s 退出', CLICK_BACK_DETAIL)
                self.device.click_adb(*CLICK_BACK_DETAIL)
                self.device.sleep(max(A.WAIT_AFTER_TAB, A.MIN_CLICK_INTERVAL))
                continue
            logger.info('AutoEquip: 离舰点 %s attempt=%s', CLICK_BACK_DETAIL, attempt)
            self.device.click_adb(*CLICK_BACK_DETAIL)
            self.device.sleep(max(A.WAIT_AFTER_TAB, A.MIN_CLICK_INTERVAL))
        logger.warning('AutoEquip: 未能确认回到六舰详情')

    def _fill_team_equipment(self, team_no: int) -> dict[str, int]:
        totals = {'ships': 0, 'filled': 0, 'no_replaceable': 0}
        logger.info('AutoEquip: 开始补齐第 %s 队装备', team_no)
        fleet_nav.open_team_details(self, team_no)

        for ship_slot in range(1, SHIP_COUNT + 1):
            fleet_nav.open_ship_detail(self, ship_slot)
            ship_stats = self._fill_empty_slots_on_current_ship()
            totals['ships'] += 1
            totals['filled'] += ship_stats['filled']
            totals['no_replaceable'] += ship_stats['no_replaceable']
            logger.info(
                'AutoEquip: 第 %s 队 slot=%s filled=%s noReplaceable=%s',
                team_no,
                ship_slot,
                ship_stats['filled'],
                ship_stats['no_replaceable'],
            )
            self.return_to_team_detail_after_ship()
            if not FleetUiNav(self)._on_team_detail():
                fleet_nav.return_to_fleet_detail(self, back_xy=CLICK_BACK_DETAIL)

        fleet_nav.return_to_main(self)
        logger.info(
            'AutoEquip: 第 %s 队完成 ships=%s filled=%s noReplaceable=%s',
            team_no,
            totals['ships'],
            totals['filled'],
            totals['no_replaceable'],
        )
        return totals

    def run(self):
        if gate_task_or_skip(self, 'ProalasAutoEquip'):
            return
        logger.hr('ProalasAutoEquip', level=1)

        quality = parse_equip_quality(self.config)
        team_no = parse_team_no(self.config)
        replace_purple = parse_replace_surplus_purple(self.config)
        allow_craft = parse_allow_craft(self.config)
        coin_limit = parse_craft_coin_limit(self.config)
        warehouse_reserve = parse_warehouse_reserve(self.config)

        logger.info(
            'AutoEquip config team=%s quality=%s replacePurple=%s allowCraft=%s '
            'coinLimit=%s warehouseReserve=%s',
            team_no,
            quality,
            replace_purple,
            allow_craft,
            coin_limit,
            warehouse_reserve,
        )

        totals = self._fill_team_equipment(team_no)
        self.ships_processed = totals['ships']
        self.equipped_count = totals['filled']
        self.slots_no_replaceable = totals['no_replaceable']

        write_auto_equip_result(
            self._config_name(),
            equipped_count=self.equipped_count,
            replaced_purple_count=self.replaced_purple_count,
            crafted_count=self.crafted_count,
            equip_quality=quality,
            team_no=team_no,
            ships_processed=self.ships_processed,
            slots_filled=self.equipped_count,
            slots_no_replaceable=self.slots_no_replaceable,
            config=self.config,
        )

        self.config.task_delay(server_update=True)
