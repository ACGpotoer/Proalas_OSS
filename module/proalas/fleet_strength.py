# -*- coding: utf-8 -*-
"""ProAlas 编队采集：状态机 + 模板验页 + 空槽过滤 → ProalasData.FleetStrength。"""
from __future__ import annotations

from module.FleetStrength import assets as A
from module.logger import logger
from module.ocr.ocr import Ocr
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.fleet_null_slot import scan_team_detail_slots
from module.proalas.fleet_ocr import ocr_bold_digits
from module.proalas.fleet_summary import compute_row_powers
from module.proalas.ui_nav import FleetUiNav
from module.proalas_collector.userdata import write_fleet_strength_team
from module.ui.ui import UI

_OCR_NAME_KW = dict(lang='cnocr', letter=(255, 255, 255), threshold=128, name='FLEET_SHIP_NAME')


def _teams_from_scope(scope: str) -> list[int]:
    scope = str(scope or 'all').strip().lower()
    if scope == 'all':
        return list(range(1, 7))
    if scope.startswith('team') and scope[4:].isdigit():
        n = int(scope[4:])
        if 1 <= n <= 6:
            return [n]
    return list(range(1, 7))


class ProalasFleetStrength(UI):
    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _ocr_name(self, area: tuple[int, int, int, int]) -> str:
        ocr = Ocr([area], **_OCR_NAME_KW)
        raw = ocr.ocr(self.device.image)
        return str(raw or '').strip()

    def _read_names_on_detail(self) -> dict[int, str]:
        names: dict[int, str] = {}
        for spec in A.SHIP_SLOTS:
            slot = int(spec['slot'])
            names[slot] = self._ocr_name(tuple(spec['name']))
        return names

    def _ocr_ship_power(self, slot: int) -> int | None:
        power = ocr_bold_digits(
            self.device.image,
            A.SHIP_POWER_BOLD_AREA,
            name=f'FLEET_SHIP_POWER_{slot}',
            lo=A.POWER_MIN,
            hi=A.POWER_MAX,
        )
        logger.info('FleetStrength slot=%s bold power=%s', slot, power)
        return power

    def _read_team_ships(self, nav: FleetUiNav) -> list[dict] | None:
        self.device.screenshot()
        scan = scan_team_detail_slots(self.device.image)
        logger.info(
            'FleetStrength null_slots=%s occupied=%s',
            scan.null_slots,
            scan.occupied_slots,
        )
        names = self._read_names_on_detail()
        powers: dict[int, int | None] = {}

        for slot, click_xy in scan.click_centers:
            if not nav.open_ship_detail(click_xy):
                nav.abort_to_main(f'进单舰失败 slot={slot}')
                return None
            powers[slot] = self._ocr_ship_power(slot)
            if not nav.return_to_team_detail():
                nav.abort_to_main(f'回六槽详情失败 slot={slot}')
                return None

        ships: list[dict] = []
        for slot in range(1, 7):
            empty = slot in scan.null_slots
            power_val = None if empty else powers.get(slot)
            ship = {
                'slot': slot,
                'name': '' if empty else names.get(slot, ''),
                'endurance': None,
                'consumption': None,
                'power': power_val,
                'empty': empty,
            }
            ships.append(ship)
            logger.info(
                'FleetStrength slot=%s name=%r power=%s empty=%s',
                slot,
                ship['name'],
                power_val,
                empty,
            )
        return ships

    def _read_team_ships_and_equip(
        self,
        nav: FleetUiNav,
        equip,
    ) -> tuple[list[dict] | None, dict[str, int]]:
        """逐舰：OCR 战力 → 同页上装备 → 回六舰详情（不重复进舰）。"""
        self.device.screenshot()
        scan = scan_team_detail_slots(self.device.image)
        logger.info(
            'FleetStrength null_slots=%s occupied=%s',
            scan.null_slots,
            scan.occupied_slots,
        )
        names = self._read_names_on_detail()
        powers: dict[int, int | None] = {}
        equip_totals = {'ships': 0, 'filled': 0, 'no_replaceable': 0}

        for slot, click_xy in scan.click_centers:
            if not nav.open_ship_detail(click_xy):
                nav.abort_to_main(f'进单舰失败 slot={slot}')
                return None, equip_totals

            powers[slot] = self._ocr_ship_power(slot)
            logger.info('FleetStrength+Equip: slot=%s 战力完成，继续上装备', slot)

            ship_stats = equip._fill_empty_slots_on_current_ship()
            equip_totals['ships'] += 1
            equip_totals['filled'] += ship_stats['filled']
            equip_totals['no_replaceable'] += ship_stats['no_replaceable']
            logger.info(
                'FleetStrength+Equip: slot=%s filled=%s noReplaceable=%s',
                slot,
                ship_stats['filled'],
                ship_stats['no_replaceable'],
            )

            equip.return_to_team_detail_after_ship()
            if not nav._on_team_detail():
                if not nav.return_to_team_detail():
                    nav.abort_to_main(f'回六槽详情失败 slot={slot}')
                    return None, equip_totals

        ships: list[dict] = []
        for slot in range(1, 7):
            empty = slot in scan.null_slots
            power_val = None if empty else powers.get(slot)
            ship = {
                'slot': slot,
                'name': '' if empty else names.get(slot, ''),
                'endurance': None,
                'consumption': None,
                'power': power_val,
                'empty': empty,
            }
            ships.append(ship)
            logger.info(
                'FleetStrength slot=%s name=%r power=%s empty=%s',
                slot,
                ship['name'],
                power_val,
                empty,
            )
        return ships, equip_totals

    def collect_fleets(self, teams: list[int]) -> bool:
        if not teams:
            return False

        nav = FleetUiNav(self)
        if not nav.goto_formation_list():
            nav.abort_to_main('进入编队列表失败')
            return False

        first_team = teams[0]
        if first_team != 1:
            nav.switch_team_on_list(first_team)

        if not nav.goto_team_detail():
            nav.abort_to_main('进入六槽详情失败')
            return False

        ok = False
        for i, team_no in enumerate(teams):
            if not 1 <= team_no <= 6:
                continue
            if i > 0:
                if not nav.switch_team_on_detail(team_no):
                    nav.abort_to_main(f'切队失败 team={team_no}')
                    return ok

            ships = self._read_team_ships(nav)
            if ships is None:
                return ok

            back, front = compute_row_powers(ships)
            total = back + front
            write_fleet_strength_team(
                self._config_name(),
                team_no,
                ships,
                back_power=back,
                front_power=front,
                total_power=total if total > 0 else None,
                config=self.config,
            )
            ok = True

        nav.goto_main()
        return ok

    def collect_and_equip_fleets(self, teams: list[int]) -> bool:
        """换船后单会话：每舰 OCR 战力后立即上装备，不重复导航进舰。"""
        if not teams:
            return False

        from module.proalas.auto_equip import ProalasAutoEquip

        equip = ProalasAutoEquip(config=self.config, device=self.device)
        nav = FleetUiNav(self)
        if not nav.goto_formation_list():
            nav.abort_to_main('进入编队列表失败')
            return False

        first_team = teams[0]
        if first_team != 1:
            nav.switch_team_on_list(first_team)

        if not nav.goto_team_detail():
            nav.abort_to_main('进入六槽详情失败')
            return False

        ok = False
        for i, team_no in enumerate(teams):
            if not 1 <= team_no <= 6:
                continue
            if i > 0:
                if not nav.switch_team_on_detail(team_no):
                    nav.abort_to_main(f'切队失败 team={team_no}')
                    return ok

            ships, equip_stats = self._read_team_ships_and_equip(nav, equip)
            if ships is None:
                return ok

            logger.info(
                'FleetStrength+Equip: team=%s equip_stats=%s',
                team_no,
                equip_stats,
            )

            back, front = compute_row_powers(ships)
            total = back + front
            write_fleet_strength_team(
                self._config_name(),
                team_no,
                ships,
                back_power=back,
                front_power=front,
                total_power=total if total > 0 else None,
                config=self.config,
            )
            ok = True

        nav.goto_main()
        return ok

    def run(self):
        if gate_task_or_skip(self, 'ProalasFleetStrength'):
            return
        logger.hr('ProalasFleetStrength', level=1)
        scope = getattr(self.config, 'ProalasFleetStrength_TeamScope', 'all')
        teams = _teams_from_scope(scope)
        logger.info('ProalasFleetStrength teams=%s scope=%s', teams, scope)
        self.collect_fleets(teams)
        self.config.task_delay(server_update=True)
