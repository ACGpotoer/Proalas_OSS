# -*- coding: utf-8 -*-
"""自动更换队伍：练级换船 → 战力采集 → 按舰自动上装备。"""
from __future__ import annotations

from datetime import datetime, timedelta

from module.logger import logger
from module.proalas.auto_fleet_change_config import (
    SWAP_TEAM_TYPES,
    parse_level_team_faction,
    parse_run_interval_days,
)
from module.proalas.fleet_team_roles import resolve_all_team_roles, resolve_team_role
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.fleet_swap import swap_level_teams
from module.proalas_collector.userdata import write_auto_fleet_change_result
from module.ui.ui import UI

TEAM_COUNT = 6


class ProalasAutoFleetChange(UI):
    def run(self):
        if gate_task_or_skip(self, 'ProalasAutoFleetChange'):
            return
        logger.hr('ProalasAutoFleetChange', level=1)
        device_id = str(getattr(self.config, 'config_name', '') or 'alas')
        interval_days = parse_run_interval_days(self.config)
        level_faction = parse_level_team_faction(self.config)
        team_rows = []
        swapped_team_ids: list[int] = []

        team_roles = resolve_all_team_roles(self.config)
        logger.info(
            'ProalasAutoFleetChange RunIntervalDays=%s LevelTeamFaction=%s 职能=%s 仅练级队换船 装备联动=开',
            interval_days,
            level_faction,
            team_roles,
        )

        level_team_ids = [
            tid for tid in range(1, TEAM_COUNT + 1)
            if team_roles.get(tid) in SWAP_TEAM_TYPES
        ]

        swap_results: dict[int, dict] = {}
        if level_team_ids:
            logger.info('ProalasAutoFleetChange: 练级换船 teams=%s（同会话）', level_team_ids)
            swap_results = swap_level_teams(self, level_team_ids, faction_pref=level_faction)

        for team_id in range(1, TEAM_COUNT + 1):
            team_type = resolve_team_role(self.config, team_id)
            logger.info('Team%s type=%s', team_id, team_type)

            row = {
                'team': team_id,
                'type': team_type,
            }

            if team_type not in SWAP_TEAM_TYPES:
                row['swapSkipped'] = True
                row['swapReason'] = 'type_not_level'
                logger.info(
                    'ProalasAutoFleetChange: 第 %s 队 type=%s 不换船（仅练级）',
                    team_id,
                    team_type,
                )
                team_rows.append(row)
                continue

            swap_stats = swap_results.get(team_id) or {}
            row['slotsAttempted'] = int(swap_stats.get('slotsAttempted', 0))
            row['slotsOk'] = int(swap_stats.get('slotsOk', 0))
            row['slotsFailed'] = int(swap_stats.get('slotsFailed', 0))
            row['swapSkipped'] = bool(swap_stats.get('skipped', False))
            if swap_stats.get('error'):
                row['swapError'] = str(swap_stats['error'])
            if int(swap_stats.get('slotsOk', 0)) > 0:
                swapped_team_ids.append(team_id)
            team_rows.append(row)

        event_flags = {}
        for evt in (1, 2):
            en = bool(getattr(self.config, f'ProalasAutoFleetChange_EventTeam{evt}Enable', False))
            event_flags[f'eventTeam{evt}'] = en
            logger.info('EventTeam%s enable=%s', evt, en)

        if swapped_team_ids:
            logger.info(
                'ProalasAutoFleetChange: 换船完成，逐舰战力+上装备 teams=%s',
                swapped_team_ids,
            )
            from module.proalas.fleet_strength import ProalasFleetStrength

            ProalasFleetStrength(config=self.config, device=self.device).collect_and_equip_fleets(
                swapped_team_ids,
            )

        next_run = datetime.now().replace(microsecond=0) + timedelta(days=interval_days)
        self.config.task_delay(target=next_run, task='ProalasAutoFleetChange')

        write_auto_fleet_change_result(
            device_id,
            teams=team_rows,
            event_flags=event_flags,
            run_interval_days=interval_days,
            next_run=next_run,
            config=self.config,
        )
        logger.info(
            'ProalasAutoFleetChange device=%s teams=%s next=%s',
            device_id,
            len(team_rows),
            next_run,
        )
