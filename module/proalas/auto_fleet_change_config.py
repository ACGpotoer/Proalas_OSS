# -*- coding: utf-8 -*-
"""自动换队：调度间隔 / 练级队阵营偏好等配置解析。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from module.proalas.dock_filter_coords import FACTION_KEYS

if TYPE_CHECKING:
    from module.config.config import AzurLaneConfig

# 仅练级队参与换船
SWAP_TEAM_TYPES = frozenset({'level'})

DEFAULT_RUN_INTERVAL_DAYS = 7
LEVEL_FACTION_OPTIONS = ['all', *FACTION_KEYS]


def parse_run_interval_days(config: 'AzurLaneConfig') -> int:
    """任务成功后隔 N 天再调度，默认 7 天。"""
    raw = getattr(config, 'ProalasAutoFleetChange_RunIntervalDays', DEFAULT_RUN_INTERVAL_DAYS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RUN_INTERVAL_DAYS
    return max(1, min(7, n))


def parse_level_team_faction(config: 'AzurLaneConfig') -> str:
    """练级队换船时船坞筛选阵营；all = 全阵营。"""
    raw = getattr(config, 'ProalasAutoFleetChange_LevelTeamFaction', 'all')
    key = str(raw or 'all').strip()
    if key not in LEVEL_FACTION_OPTIONS:
        return 'all'
    return key
