# -*- coding: utf-8 -*-
"""读取服务器象限（黄/绿/蓝）→ 写设备 config（活动开关 / Scheduler / GachaUp / PlanGreen）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import module.config.server as server_mod
from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.logger import logger
from module.proalas.plan_server_quadrants import get_server_quadrants

# 无活动时：关 Event/Gacha/活动修正/UP检测等；**不**强制关 ProalasAutoEventShop（商店兑换可继续）
_NONE_SCHEDULER_DEFAULTS: dict[str, bool] = {
    'Event': False,
    'Event2': False,
    'EventA': False,
    'EventB': False,
    'EventC': False,
    'EventD': False,
    'EventSp': False,
    'Raid': False,
    'RaidDaily': False,
    'Gacha': False,
    'Main': True,
    'Main2': True,
    'Main3': False,
    'GemsFarming': False,
    'ProalasGachaCheck': False,
    'ProalasEventFormatFix': False,
    'ProalasCollectionFill': False,
}

_NONE_SCHEDULER_GEM: dict[str, bool] = {
    'Main': False,
    'Main2': False,
    'GemsFarming': True,
}


@dataclass
class MaterializeResult:
    device_id: str
    date: str
    applied: int = 0
    details: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    blue: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _load_valid_event_ids() -> set[str]:
    """从 campaign/Readme.md 读取所有已注册的事件目录名。"""
    import re
    path = os.path.normpath('./campaign/Readme.md')
    if not os.path.isfile(path):
        logger.warning('ActivityMaterializer campaign/Readme.md not found, skip event validation')
        return set()
    valid: set[str] = set()
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if not re.search(r'^\|.+\|$', line):
                    continue
                parts = [x.strip() for x in line.strip('| \n').split('|')]
                if len(parts) != 7:
                    continue
                directory = parts[1].replace(' ', '_')
                if re.search(r'\d{8}', directory):
                    valid.add(directory)
    except OSError as e:
        logger.warning('ActivityMaterializer failed to read Readme.md: %s', e)
    return valid


def _ensure_task_bucket(data: dict[str, Any], task: str) -> None:
    if task not in data or not isinstance(data.get(task), dict):
        data[task] = {}


def _apply_campaign_events(
    data: dict[str, Any],
    mapping: dict[str, Any],
    details: list[str],
    *,
    valid_event_ids: set[str] | None = None,
) -> int:
    count = 0
    skipped: list[str] = []
    for task, event_id in (mapping or {}).items():
        task = str(task).strip()
        event_id = str(event_id).strip()
        if not task or not event_id:
            continue
        if valid_event_ids is not None and event_id not in valid_event_ids:
            skipped.append(f'{task}={event_id}')
            continue
        _ensure_task_bucket(data, task)
        deep_set(data, keys=[task, 'Campaign', 'Event'], value=event_id)
        details.append(f'Campaign.Event {task}={event_id}')
        count += 1
    if skipped:
        logger.warning(
            'ActivityMaterializer skipped stale campaign_events (not in Readme.md): %s',
            '; '.join(skipped),
        )
    return count


def _apply_scheduler_enable(data: dict[str, Any], mapping: dict[str, Any], details: list[str]) -> int:
    count = 0
    for task, enabled in (mapping or {}).items():
        task = str(task).strip()
        if not task:
            continue
        _ensure_task_bucket(data, task)
        deep_set(data, keys=[task, 'Scheduler', 'Enable'], value=bool(enabled))
        details.append(f'Scheduler.Enable {task}={bool(enabled)}')
        count += 1
    return count


def _apply_gacha_meta(data: dict[str, Any], gacha: dict[str, Any], details: list[str]) -> int:
    if not isinstance(gacha, dict):
        return 0
    up_ships = [str(x).strip() for x in (gacha.get('up_ships') or []) if str(x).strip()]
    if not up_ships and gacha.get('stop_if_owned') is None:
        return 0
    block = {
        'upShips': up_ships,
        'stopIfOwned': bool(gacha.get('stop_if_owned', True)),
        'syncedAt': datetime.now().isoformat(timespec='seconds'),
        'sourceDate': _today_str(),
        'allOwned': None,
        'lastCheckAt': '',
    }
    proalas = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas, dict):
        proalas = {}
    proalas['GachaUp'] = block
    deep_set(data, keys=['ProalasData'], value=proalas)
    details.append(f'ProalasData.GachaUp upShips={up_ships}')
    return 1


def _apply_farm_meta(data: dict[str, Any], blue: dict[str, Any], details: list[str]) -> int:
    if not isinstance(blue, dict):
        return 0
    farm_ships = [str(x).strip() for x in (blue.get('farm_ships') or []) if str(x).strip()]
    if not farm_ships:
        return 0
    proalas = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas, dict):
        proalas = {}
    fill = dict(proalas.get('CollectionFill') or {})
    farm = dict(fill.get('farm') or {})
    farm['targets'] = farm_ships
    farm['syncedAt'] = datetime.now().isoformat(timespec='seconds')
    farm.setdefault('activeTarget', '')
    farm.setdefault('activeStage', '')
    fill['farm'] = farm
    proalas['CollectionFill'] = fill
    deep_set(data, keys=['ProalasData'], value=proalas)
    details.append(f'ProalasData.CollectionFill.farm.targets={farm_ships}')
    return 1


def _apply_green_meta(data: dict[str, Any], green: dict[str, Any], details: list[str]) -> int:
    if not isinstance(green, dict) or not green:
        return 0
    proalas = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas, dict):
        proalas = {}
    block = {
        'note': str(green.get('note') or ''),
        'manualWindow': bool(green.get('manual_window', True)),
        'syncedAt': datetime.now().isoformat(timespec='seconds'),
    }
    if green.get('pause_bot') is not None:
        block['pauseBot'] = bool(green.get('pause_bot'))
    proalas['PlanGreen'] = block
    deep_set(data, keys=['ProalasData'], value=proalas)
    details.append('ProalasData.PlanGreen')
    return 1


_EVENT_FORMAT_ALAS = frozenset({'T-HT', 'AB-CD', 'SP-HSP'})


def _apply_event_format(data: dict[str, Any], event_format: str, details: list[str]) -> int:
    fmt = str(event_format or '').strip()
    if not fmt or fmt == 'NONE':
        return 0
    if fmt not in _EVENT_FORMAT_ALAS:
        logger.warning('ActivityMaterializer skip unknown event_format=%r', fmt)
        return 0
    _ensure_task_bucket(data, 'ProalasEventFormatFix')
    deep_set(data, keys=['ProalasEventFormatFix', 'ProalasEventFormatFix', 'Template'], value=fmt)
    proalas = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas, dict):
        proalas = {}
    proalas['EventFormat'] = {
        'template': fmt,
        'syncedAt': datetime.now().isoformat(timespec='seconds'),
        'sourceDate': _today_str(),
    }
    deep_set(data, keys=['ProalasData'], value=proalas)
    details.append(f'ProalasEventFormatFix.Template={fmt}')
    return 1


def build_patches_from_blue(blue: dict[str, Any]) -> dict[str, Any]:
    """纯函数：蓝色 payload → 待写入片段（供 HostAgent 复用）。"""
    mode = str(blue.get('mode') or 'event').lower()
    scheduler = dict(blue.get('scheduler_enable') or {})
    campaigns = dict(blue.get('campaign_events') or {})
    gacha = dict(blue.get('gacha') or {}) if isinstance(blue.get('gacha'), dict) else {}
    event_format = str(blue.get('event_format') or '').strip()

    if mode == 'none':
        base = dict(_NONE_SCHEDULER_DEFAULTS)
        base.update(scheduler)
        scheduler = base
    return {
        'mode': mode,
        'campaign_events': campaigns,
        'scheduler_enable': scheduler,
        'gacha': gacha,
        'event_format': event_format,
    }


def materialize_activity(
    device_id: str,
    *,
    on_date: Optional[str] = None,
    dry_run: bool = False,
    allow_manifest_fallback: bool = True,
) -> MaterializeResult:
    device_id = str(device_id or '').strip()
    date_str = str(on_date or _today_str())
    server = getattr(server_mod, 'server', 'cn')

    from module.proalas.plan_quadrant_view import get_blue_payload
    from module.proalas.quadrant_policy import merge_scheduler_maps

    quads = get_server_quadrants(device_id, date_str, server=server)
    blue = quads.get('blue') or get_blue_payload(
        device_id, date_str, server=server, allow_manifest_fallback=allow_manifest_fallback,
    )
    yellow = quads.get('yellow') or {}
    green = quads.get('green') or {}

    result = MaterializeResult(device_id=device_id, date=date_str, blue=blue, dry_run=dry_run)

    if not blue and not yellow.get('scheduler_enable') and not green:
        result.details.append('no server quadrant payload (blue/yellow/green)')
        return result

    path = filepath_config(device_id)
    data = read_file(path)
    if not isinstance(data, dict):
        result.errors.append(f'config missing: {path}')
        return result

    proalas_backup = deep_get(data, ['ProalasData'], None)
    blue_patches = build_patches_from_blue(blue or {})
    yellow_sched = dict(yellow.get('scheduler_enable') or {}) if isinstance(yellow, dict) else {}
    merged_sched = merge_scheduler_maps(yellow_sched, blue_patches.get('scheduler_enable') or {})

    if blue_patches.get('mode') == 'none':
        pref = str(deep_get(data, ['ProalasData', 'ResourcePreference'], 'material') or 'material').lower().strip()
        if pref == 'gem':
            merged_sched = merge_scheduler_maps(merged_sched, _NONE_SCHEDULER_GEM)
            result.details.append('ResourcePreference=gem (GemsFarming on, Main off)')
        else:
            result.details.append('ResourcePreference=material (Main on, GemsFarming off)')

    valid_ids = _load_valid_event_ids()
    result.applied += _apply_campaign_events(
        data, blue_patches.get('campaign_events') or {}, result.details,
        valid_event_ids=valid_ids,
    )

    mode = str(blue_patches.get('mode', 'event'))
    no_event = mode == 'none' or not blue_patches.get('campaign_events')
    proalas_data = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas_data, dict):
        proalas_data = {}
    proalas_data['SkipEventPt'] = no_event
    deep_set(data, keys=['ProalasData'], value=proalas_data)
    if no_event:
        result.details.append('ProalasData.SkipEventPt=True')

    result.applied += _apply_scheduler_enable(data, merged_sched, result.details)
    result.applied += _apply_gacha_meta(data, blue_patches.get('gacha') or {}, result.details)
    result.applied += _apply_farm_meta(data, blue or {}, result.details)
    result.applied += _apply_event_format(data, blue_patches.get('event_format') or '', result.details)
    result.applied += _apply_green_meta(data, green, result.details)

    if proalas_backup is not None and isinstance(proalas_backup, dict):
        merged = dict(proalas_backup)
        for key in ('GachaUp', 'CollectionFill', 'PlanGreen', 'EventFormat', 'SkipEventPt'):
            new_val = deep_get(data, ['ProalasData', key], None)
            if new_val is not None:
                merged[key] = new_val
        deep_set(data, keys=['ProalasData'], value=merged)

    if dry_run:
        logger.info(
            'ActivityMaterializer dry-run device=%s date=%s applied=%s',
            device_id, date_str, result.applied,
        )
        return result

    if result.applied > 0:
        write_file(path, data)
        logger.info(
            'ActivityMaterializer device=%s date=%s applied=%s details=%s',
            device_id, date_str, result.applied, '; '.join(result.details[:8]),
        )
    return result
