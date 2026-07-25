# -*- coding: utf-8 -*-
"""读写 Alas 配置文件 ./config/{config_name}.json 中的 ProalasData。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.logger import logger
from module.proalas.resource_history_store import (
    RESOURCE_HISTORY_PATH,
    append_resource_history_to_data,
)

if TYPE_CHECKING:
    from module.config.config import AzurLaneConfig

FLEET_STRENGTH_PATH = ('ProalasData', 'FleetStrength')
GAME_RESOURCE_PATH = ('ProalasData', 'GameResource')
COLLECTOR_META_PATH = ('ProalasData', 'CollectorMeta')
AUTO_BREAK_PATH = ('ProalasData', 'AutoBreak')
AUTO_EQUIP_PATH = ('ProalasData', 'AutoEquip')
AUTO_EXP_BOOK_PATH = ('ProalasData', 'AutoExpBook')
AUTO_FLEET_CHANGE_PATH = ('ProalasData', 'AutoFleetChange')
EXP_BOOK_PATH = ('ProalasData', 'ExpBook')

FIELD_MAP = {
    'oil': 'oil',
    'money': 'money',
    'rmb': 'Rmb',
    'cube': 'cube',
    'act_pt': 'Act-Pt',
    'boat_rate': 'BoatRate',
    'boat_max': 'BoatMax',
    'boat_dock': 'BoatDock',
}


def _default_game_resource() -> dict[str, Any]:
    return {
        'oil': 0,
        'money': 0,
        'cube': 0,
        'BoatRate': 0.0,
        'BoatMax': 0,
        'BoatDock': '',
        'Rmb': 0,
        'Act-Pt': 0,
        'syncedAt': '',
    }


def _load_config_data(config_name: str) -> dict:
    path = filepath_config(config_name)
    if not os.path.isfile(path):
        return {}
    return read_file(path)


def _preserve_scheduler_from_runtime(
    data: dict,
    config_name: str,
    config: Optional['AzurLaneConfig'],
) -> None:
    """ProalasData 整文件写回时保留运行时 Scheduler（含 >24h 的 NextRun）。"""
    if config is None:
        return
    if str(getattr(config, 'config_name', '')) != str(config_name):
        return
    runtime = getattr(config, 'data', None)
    if not isinstance(runtime, dict):
        return
    for task_name, task_body in runtime.items():
        if not isinstance(task_body, dict):
            continue
        sched = task_body.get('Scheduler')
        if isinstance(sched, dict):
            deep_set(data, [task_name, 'Scheduler'], dict(sched))


def _sync_proalas_to_runtime_config(
    data: dict,
    config_name: str,
    config: Optional['AzurLaneConfig'],
) -> None:
    """避免 task_delay → config.save() 用旧内存覆盖刚写入的 ProalasData。"""
    if config is None:
        return
    if str(getattr(config, 'config_name', '')) != str(config_name):
        return
    gr = deep_get(data, list(GAME_RESOURCE_PATH), None)
    meta = deep_get(data, list(COLLECTOR_META_PATH), None)
    fs = deep_get(data, list(FLEET_STRENGTH_PATH), None)
    ab = deep_get(data, list(AUTO_BREAK_PATH), None)
    ae = deep_get(data, list(AUTO_EQUIP_PATH), None)
    eb = deep_get(data, list(EXP_BOOK_PATH), None)
    rh = deep_get(data, list(RESOURCE_HISTORY_PATH), None)
    if isinstance(gr, dict):
        deep_set(config.data, list(GAME_RESOURCE_PATH), gr)
    if isinstance(meta, dict):
        deep_set(config.data, list(COLLECTOR_META_PATH), meta)
    if isinstance(fs, dict):
        deep_set(config.data, list(FLEET_STRENGTH_PATH), fs)
    if isinstance(ab, dict):
        deep_set(config.data, list(AUTO_BREAK_PATH), ab)
    if isinstance(ae, dict):
        deep_set(config.data, list(AUTO_EQUIP_PATH), ae)
    if isinstance(eb, dict):
        deep_set(config.data, list(EXP_BOOK_PATH), eb)
    if isinstance(rh, dict):
        deep_set(config.data, list(RESOURCE_HISTORY_PATH), rh)


def _save_config_data(
    config_name: str,
    data: dict,
    *,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    try:
        _preserve_scheduler_from_runtime(data, config_name, config)
        _sync_proalas_to_runtime_config(data, config_name, config)
        write_file(filepath_config(config_name), data)
        logger.info('ProalasData saved config=%s', config_name)
        return True
    except Exception as e:
        logger.error('ProalasData save failed config=%s: %s', config_name, e)
        return False


def read_game_resource(config_name: str) -> dict[str, Any]:
    data = _load_config_data(config_name)
    gr = deep_get(data, list(GAME_RESOURCE_PATH), None)
    if isinstance(gr, dict):
        return gr
    return {}


def read_resource_history(config_name: str) -> dict[str, Any]:
    data = _load_config_data(config_name)
    hist = deep_get(data, list(RESOURCE_HISTORY_PATH), None)
    if isinstance(hist, dict):
        return hist
    return {}


def read_proalas_row(config_name: str) -> dict[str, Any]:
    return {'GameResource': read_game_resource(config_name)}


def read_boat_max(config_name: str, *_unused, **__unused) -> int:
    gr = read_game_resource(config_name)
    try:
        mx = int(gr.get('BoatMax') or 0)
    except (TypeError, ValueError):
        mx = 0
    if mx > 0:
        return mx
    from module.proalas_collector.log_sync import read_boat_max_from_logs

    mx = read_boat_max_from_logs(config_name)
    return mx if mx > 0 else 0


def _merge_game_resource(data: dict, patch: dict[str, Any]) -> None:
    gr = deep_get(data, list(GAME_RESOURCE_PATH), None)
    if not isinstance(gr, dict):
        gr = _default_game_resource()
        deep_set(data, list(GAME_RESOURCE_PATH), gr)
    for src, dst in FIELD_MAP.items():
        if src not in patch or patch[src] is None:
            continue
        if src in ('oil', 'money', 'rmb') and patch[src] == 0:
            continue
        gr[dst] = patch[src]
    gr['syncedAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def write_collector_snapshot(
    config_name: str,
    snapshot: dict[str, Any],
    *,
    user_data_path: Optional[str] = None,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    _ = user_data_path
    if not config_name:
        logger.error('ProalasData: config_name empty')
        return False
    data = _load_config_data(config_name)
    _merge_game_resource(data, snapshot)
    append_resource_history_to_data(data, snapshot)
    deep_set(
        data,
        list(COLLECTOR_META_PATH),
        {
            'lastRunAt': datetime.now().isoformat(timespec='seconds'),
            'snapshot': {k: snapshot[k] for k in snapshot if snapshot[k] is not None},
        },
    )
    return _save_config_data(config_name, data, config=config)


def write_boat_rate(
    config_name: str,
    rate: float,
    *,
    user_data_path: Optional[str] = None,
    config: Optional['AzurLaneConfig'] = None,
    boat_max: Optional[int] = None,
) -> bool:
    _ = user_data_path
    patch: dict[str, Any] = {'boat_rate': round(float(rate), 3)}
    if boat_max is not None and boat_max > 0:
        patch['boat_max'] = int(boat_max)
    return write_collector_snapshot(config_name, patch, config=config)


read_user_row = read_proalas_row


def _default_fleet_strength() -> dict:
    return {
        'updatedAt': None,
        'teams': [
            {
                'team': i,
                'backPower': 0,
                'frontPower': 0,
                'ships': [
                    {
                        'slot': s,
                        'name': '',
                        'endurance': None,
                        'consumption': None,
                        'power': None,
                        'empty': True,
                    }
                    for s in range(1, 7)
                ],
            }
            for i in range(1, 7)
        ],
    }


def write_fleet_strength_team(
    config_name: str,
    team_no: int,
    ships: list[dict],
    *,
    back_power: int,
    front_power: int,
    total_power: int | None = None,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    if not config_name:
        return False
    data = _load_config_data(config_name)
    fs = deep_get(data, list(FLEET_STRENGTH_PATH), None)
    if not isinstance(fs, dict) or not isinstance(fs.get('teams'), list):
        fs = _default_fleet_strength()
        deep_set(data, list(FLEET_STRENGTH_PATH), fs)
    teams = fs.get('teams') or []
    updated = False
    for team in teams:
        if not isinstance(team, dict):
            continue
        if int(team.get('team', 0)) != int(team_no):
            continue
        team['backPower'] = int(back_power)
        team['frontPower'] = int(front_power)
        team['ships'] = ships
        if total_power is not None:
            team['totalPower'] = int(total_power)
        updated = True
        break
    if not updated:
        teams.append({
            'team': int(team_no),
            'backPower': int(back_power),
            'frontPower': int(front_power),
            'ships': ships,
            **({'totalPower': int(total_power)} if total_power is not None else {}),
        })
        fs['teams'] = teams
    fs['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    deep_set(data, list(FLEET_STRENGTH_PATH), fs)
    logger.info(
        'ProalasData FleetStrength saved config=%s team=%s back=%s front=%s',
        config_name,
        team_no,
        back_power,
        front_power,
    )
    return _save_config_data(config_name, data, config=config)


def write_auto_break_result(
    config_name: str,
    *,
    breakthrough_count: int,
    can_breakthrough: bool,
    star_quality: str,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    if not config_name:
        logger.error('ProalasData AutoBreak: config_name empty')
        return False
    today = datetime.now().strftime('%Y-%m-%d')
    data = _load_config_data(config_name)
    prev = deep_get(data, list(AUTO_BREAK_PATH), None)
    prev_today = 0
    if isinstance(prev, dict) and str(prev.get('todayDate') or '') == today:
        try:
            prev_today = int(prev.get('todayCount') or 0)
        except (TypeError, ValueError):
            prev_today = 0
    payload = {
        'lastRunAt': datetime.now().isoformat(timespec='seconds'),
        'breakthroughCount': int(breakthrough_count),
        'canBreakthrough': bool(can_breakthrough),
        'starQuality': str(star_quality),
        'todayDate': today,
        'todayCount': prev_today + int(breakthrough_count),
    }
    deep_set(data, list(AUTO_BREAK_PATH), payload)
    logger.info(
        'ProalasData AutoBreak saved config=%s count=%s todayTotal=%s star=%s',
        config_name,
        breakthrough_count,
        payload['todayCount'],
        star_quality,
    )
    return _save_config_data(config_name, data, config=config)


def write_auto_equip_result(
    config_name: str,
    *,
    equipped_count: int,
    replaced_purple_count: int,
    crafted_count: int,
    equip_quality: str,
    warehouse_current: int = 0,
    warehouse_spare: int = 0,
    warehouse_total: int = 0,
    team_no: int = 0,
    ships_processed: int = 0,
    slots_filled: int = 0,
    slots_no_replaceable: int = 0,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    if not config_name:
        logger.error('ProalasData AutoEquip: config_name empty')
        return False
    payload = {
        'lastRunAt': datetime.now().isoformat(timespec='seconds'),
        'equippedCount': int(equipped_count),
        'replacedPurpleCount': int(replaced_purple_count),
        'craftedCount': int(crafted_count),
        'equipQuality': str(equip_quality),
        'teamNo': int(team_no),
        'shipsProcessed': int(ships_processed),
        'slotsFilled': int(slots_filled),
        'slotsNoReplaceable': int(slots_no_replaceable),
        'warehouseCurrent': int(warehouse_current),
        'warehouseSpare': int(warehouse_spare),
        'warehouseTotal': int(warehouse_total),
        'warehouseText': (
            f'{int(warehouse_current)}/{int(warehouse_total)}'
            if warehouse_total > 0 else ''
        ),
    }
    data = _load_config_data(config_name)
    deep_set(data, list(AUTO_EQUIP_PATH), payload)
    logger.info(
        'ProalasData AutoEquip saved config=%s equip=%s replace=%s craft=%s quality=%s',
        config_name,
        equipped_count,
        replaced_purple_count,
        crafted_count,
        equip_quality,
    )
    return _save_config_data(config_name, data, config=config)


def read_auto_exp_book_status(config_name: str) -> dict[str, Any]:
    data = _load_config_data(config_name)
    raw = deep_get(data, list(AUTO_EXP_BOOK_PATH), None)
    return dict(raw) if isinstance(raw, dict) else {}


def write_auto_exp_book_result(
    config_name: str,
    *,
    feed_rounds_target: int,
    feed_rounds_done: int,
    ship_rarity: str,
    status: str,
    status_label: str,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    if not config_name:
        logger.error('ProalasData AutoExpBook: config_name empty')
        return False
    payload = {
        'lastRunAt': datetime.now().isoformat(timespec='seconds'),
        'feedRoundsTarget': int(feed_rounds_target),
        'feedRoundsDone': int(feed_rounds_done),
        'shipRarity': str(ship_rarity),
        'status': str(status),
        'statusLabel': str(status_label),
    }
    data = _load_config_data(config_name)
    deep_set(data, list(AUTO_EXP_BOOK_PATH), payload)
    logger.info(
        'ProalasData AutoExpBook saved config=%s rounds=%s/%s status=%s',
        config_name,
        feed_rounds_done,
        feed_rounds_target,
        status,
    )
    return _save_config_data(config_name, data, config=config)


ACTIVE_FLEET_TEAMS = [3, 4]


def write_auto_fleet_change_result(
    config_name: str,
    *,
    teams: list[dict[str, Any]],
    event_flags: Optional[dict[str, Any]] = None,
    run_interval_days: Optional[int] = None,
    next_run: Optional[datetime] = None,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    if not config_name:
        logger.error('ProalasData AutoFleetChange: config_name empty')
        return False
    payload: dict[str, Any] = {
        'lastRunAt': datetime.now().isoformat(timespec='seconds'),
        'teams': list(teams or []),
        'activeTeams': list(ACTIVE_FLEET_TEAMS),
    }
    if run_interval_days is not None:
        payload['runIntervalDays'] = int(run_interval_days)
    if next_run is not None:
        payload['nextRunAt'] = next_run.isoformat(sep=' ', timespec='seconds')
    if isinstance(event_flags, dict):
        payload.update(event_flags)
    data = _load_config_data(config_name)
    deep_set(data, list(AUTO_FLEET_CHANGE_PATH), payload)
    logger.info(
        'ProalasData AutoFleetChange saved config=%s teamRuns=%s',
        config_name,
        len(teams or []),
    )
    return _save_config_data(config_name, data, config=config)


def read_exp_book_meta(config_name: str) -> dict[str, Any]:
    if not config_name:
        return {}
    data = _load_config_data(config_name)
    meta = deep_get(data, list(EXP_BOOK_PATH), None)
    return dict(meta) if isinstance(meta, dict) else {}


def read_exp_book_value(config_name: str) -> int:
    meta = read_exp_book_meta(config_name)
    try:
        return int(meta.get('exp') or 0)
    except (TypeError, ValueError):
        return 0


def write_exp_book_result(
    config_name: str,
    *,
    exp_value: int,
    got_exp: bool,
    used_exp: bool,
    threshold: int,
    config: Optional['AzurLaneConfig'] = None,
) -> bool:
    if not config_name:
        logger.error('ProalasData ExpBook: config_name empty')
        return False
    today = datetime.now().strftime('%Y-%m-%d')
    data = _load_config_data(config_name)
    prev = deep_get(data, list(EXP_BOOK_PATH), None)
    prev_today_get = 0
    if isinstance(prev, dict) and str(prev.get('todayDate') or '') == today:
        try:
            prev_today_get = int(prev.get('todayGetCount') or 0)
        except (TypeError, ValueError):
            prev_today_get = 0
    today_get_inc = 1 if got_exp else 0
    payload = {
        'exp': int(exp_value),
        'lastRunAt': datetime.now().isoformat(timespec='seconds'),
        'gotExp': bool(got_exp),
        'usedExp': bool(used_exp),
        'useExpThreshold': int(threshold),
        'todayDate': today,
        'todayGetCount': prev_today_get + today_get_inc,
    }
    deep_set(data, list(EXP_BOOK_PATH), payload)
    logger.attr('EXP_BOOK', int(exp_value))
    logger.info(
        'ProalasData ExpBook saved config=%s exp=%s got=%s used=%s todayGet=%s',
        config_name,
        exp_value,
        got_exp,
        used_exp,
        payload['todayGetCount'],
    )
    return _save_config_data(config_name, data, config=config)
