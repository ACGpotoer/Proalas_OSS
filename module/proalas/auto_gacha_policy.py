# -*- coding: utf-8 -*-
"""自动 UP 抽卡补齐：门禁与预算计算（纯函数，便于单测）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module.config.deep import deep_get
from module.config.utils import get_server_last_update

# 产品硬限制（代码级，不随 WebUI 改动）
HARD_CUBE_FLOOR = 500
HARD_CUBE_DAILY_MAX = 20
EVENT_CUBE_COST = 2
GACHA_AMOUNT_SCHEMA_MAX = 10


@dataclass(frozen=True)
class AutoGachaGate:
    ok: bool
    reason: str
    pull_count: int = 0


def server_day_key() -> str:
    return get_server_last_update('04:00').strftime('%Y-%m-%d')


def _today_pulls(gacha_auto: dict[str, Any]) -> int:
    day = str(gacha_auto.get('date') or '').strip()
    if day != server_day_key():
        return 0
    raw = gacha_auto.get('todayPulls', 0)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def evaluate_auto_gacha(
    config_data: dict[str, Any],
    *,
    cubes: int | None = None,
    event_day: bool | None = None,
) -> AutoGachaGate:
    """判断是否允许自动抽卡，并计算本次可抽发数。"""
    from module.proalas.collection_fill_policy import build_fill_enabled, collection_fill_enabled

    if not collection_fill_enabled(config_data):
        return AutoGachaGate(False, 'collection_fill_disabled')
    if not build_fill_enabled(config_data):
        return AutoGachaGate(False, 'build_fill_disabled')

    enabled = bool(deep_get(
        config_data,
        ['ProalasCollectionFill', 'ProalasCollectionFill', 'AutoGachaEnable'],
        False,
    ))
    if not enabled:
        return AutoGachaGate(False, 'auto_gacha_disabled')

    if bool(deep_get(config_data, ['Gacha', 'Scheduler', 'Enable'], False)):
        return AutoGachaGate(False, 'builtin_gacha_scheduler_enabled')

    gacha_up = deep_get(config_data, ['ProalasData', 'GachaUp'], {}) or {}
    if not isinstance(gacha_up, dict):
        gacha_up = {}

    if gacha_up.get('partial'):
        return AutoGachaGate(False, 'gacha_check_partial')

    missing = [
        str(x).strip()
        for x in (gacha_up.get('missing') or [])
        if str(x).strip()
    ]
    if not missing and gacha_up.get('recommendGacha') is not True:
        if gacha_up.get('allOwned') is True:
            return AutoGachaGate(False, 'all_up_owned')
        return AutoGachaGate(False, 'not_recommended')

    reserve_cfg = deep_get(
        config_data,
        ['ProalasCollectionFill', 'ProalasCollectionFill', 'CubeReserveMin'],
        HARD_CUBE_FLOOR,
    )
    try:
        reserve = max(HARD_CUBE_FLOOR, int(reserve_cfg))
    except (TypeError, ValueError):
        reserve = HARD_CUBE_FLOOR

    if cubes is None:
        cubes = _read_cubes_from_data(config_data)
    if cubes is None:
        return AutoGachaGate(False, 'cube_unknown')
    if cubes < reserve:
        return AutoGachaGate(False, f'cube_below_reserve({cubes}<{reserve})')

    if event_day is False:
        return AutoGachaGate(False, 'not_event_day')

    gacha_auto = deep_get(config_data, ['ProalasData', 'GachaAuto'], {}) or {}
    if not isinstance(gacha_auto, dict):
        gacha_auto = {}
    today_pulls = _today_pulls(gacha_auto)
    daily_remaining = max(0, HARD_CUBE_DAILY_MAX - today_pulls)
    if daily_remaining <= 0:
        return AutoGachaGate(False, 'daily_limit_reached')

    max_per_run = deep_get(
        config_data,
        ['ProalasCollectionFill', 'ProalasCollectionFill', 'CubeMaxPerRun'],
        6,
    )
    try:
        max_per_run = max(1, min(int(max_per_run), GACHA_AMOUNT_SCHEMA_MAX))
    except (TypeError, ValueError):
        max_per_run = 6

    spendable = max(0, cubes - reserve)
    max_by_cubes = spendable // EVENT_CUBE_COST
    pull_count = min(max_per_run, daily_remaining, max_by_cubes)
    if pull_count <= 0:
        return AutoGachaGate(False, 'no_affordable_pulls')

    return AutoGachaGate(True, 'ok', pull_count=pull_count)


def _read_cubes_from_data(config_data: dict[str, Any]) -> int | None:
    gr = deep_get(config_data, ['ProalasData', 'GameResource'], {}) or {}
    if isinstance(gr, dict):
        raw = gr.get('BuildCube', gr.get('cube'))
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    return None
