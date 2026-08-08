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

# 无活动时：关 Event/共斗/Gacha/活动检测等；**不**强制关 ProalasAutoEventShop（商店兑换可继续）
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
    'Coalition': False,
    'Gacha': False,
    'Main': True,
    'Main2': True,
    'Main3': False,
    'GemsFarming': False,
    'ProalasGachaCheck': False,
    'ProalasEventFormatFix': False,
    'ProalasCollectionFill': False,
}

# mode=none 时这些任务禁止被蓝区 scheduler_enable 残留重新打开
_EVENT_RELATED_FORCE_OFF: tuple[str, ...] = (
    'Event',
    'Event2',
    'EventA',
    'EventB',
    'EventC',
    'EventD',
    'EventSp',
    'Raid',
    'RaidDaily',
    'Coalition',
    'Gacha',
    'ProalasGachaCheck',
    'ProalasEventFormatFix',
    'ProalasCollectionFill',
)

# 无活动时把活动目录写回主线，避免活动检测仍读到旧 coalition_/event_
_NONE_CAMPAIGN_RESET: dict[str, str] = {
    'Event': 'campaign_main',
    'Event2': 'campaign_main',
    'EventA': 'campaign_main',
    'EventB': 'campaign_main',
    'EventC': 'campaign_main',
    'EventD': 'campaign_main',
    'EventSp': 'campaign_main',
    'Coalition': 'campaign_main',
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


_EVENT_FORMAT_ALAS = frozenset({'T-HT', 'AB-CD', 'SP-HSP', 'COALITION', 'NONE'})


def _apply_event_format(data: dict[str, Any], event_format: str, details: list[str]) -> int:
    fmt = str(event_format or '').strip().upper()
    if not fmt:
        return 0
    if fmt not in _EVENT_FORMAT_ALAS:
        logger.warning('ActivityMaterializer skip unknown event_format=%r', fmt)
        return 0
    _ensure_task_bucket(data, 'ProalasEventFormatFix')
    # UI Template 选项暂无 COALITION/NONE：共斗以 Campaign.Event=coalition_* + ProalasData.EventFormat 为准
    if fmt not in ('COALITION', 'NONE'):
        deep_set(data, keys=['ProalasEventFormatFix', 'ProalasEventFormatFix', 'Template'], value=fmt)
    if fmt == 'NONE':
        deep_set(data, keys=['ProalasEventFormatFix', 'ProalasEventFormatFix', 'AllCleared'], value=False)
        deep_set(data, keys=['ProalasEventFormatFix', 'ProalasEventFormatFix', 'StopStage'], value='')
    proalas = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas, dict):
        proalas = {}
    proalas['EventFormat'] = {
        'template': fmt,
        'syncedAt': datetime.now().isoformat(timespec='seconds'),
        'sourceDate': _today_str(),
    }
    deep_set(data, keys=['ProalasData'], value=proalas)
    details.append(f'ProalasData.EventFormat={fmt}')
    return 1


def _apply_none_campaign_reset(data: dict[str, Any], details: list[str]) -> int:
    """无活动日：活动任务 Campaign.Event 写回 campaign_main。"""
    count = 0
    for task, event_id in _NONE_CAMPAIGN_RESET.items():
        cur = str(deep_get(data, [task, 'Campaign', 'Event'], '') or '').strip()
        if cur in ('', event_id):
            continue
        _ensure_task_bucket(data, task)
        deep_set(data, keys=[task, 'Campaign', 'Event'], value=event_id)
        details.append(f'Campaign.Event {task}={event_id} (none-day reset)')
        count += 1
    return count


def _blue_is_event_payload(blue: dict[str, Any] | None) -> bool:
    """蓝区是否表示「有活动」。空蓝区 / 无 mode / mode=none → 否。"""
    if not isinstance(blue, dict) or not blue:
        return False
    mode = str(blue.get('mode') or '').strip().lower()
    if mode == 'event':
        return True
    if mode == 'none':
        return False
    fmt = str(blue.get('event_format') or '').strip().upper()
    if fmt and fmt not in ('NONE',):
        return True
    campaigns = blue.get('campaign_events') or {}
    if isinstance(campaigns, dict) and any(str(v or '').strip() for v in campaigns.values()):
        return True
    sched = blue.get('scheduler_enable') or {}
    if isinstance(sched, dict):
        for key in _EVENT_RELATED_FORCE_OFF:
            if key in ('ProalasGachaCheck', 'ProalasEventFormatFix', 'ProalasCollectionFill', 'Gacha'):
                continue
            if sched.get(key):
                return True
    return False


def build_patches_from_blue(blue: dict[str, Any]) -> dict[str, Any]:
    """纯函数：蓝色 payload → 待写入片段（供 HostAgent 复用）。"""
    blue = blue if isinstance(blue, dict) else {}
    # 空蓝区 / 未写 mode → 按无活动处理（旧逻辑默认 event 会导致残留活动开关永不清理）
    if not blue or not str(blue.get('mode') or '').strip():
        mode = 'none' if not _blue_is_event_payload(blue) else 'event'
    else:
        mode = str(blue.get('mode') or '').strip().lower()
        if mode not in ('event', 'none'):
            mode = 'event' if _blue_is_event_payload(blue) else 'none'

    scheduler = dict(blue.get('scheduler_enable') or {})
    campaigns = dict(blue.get('campaign_events') or {})
    gacha = dict(blue.get('gacha') or {}) if isinstance(blue.get('gacha'), dict) else {}
    event_format = str(blue.get('event_format') or '').strip()

    if mode == 'none':
        base = dict(_NONE_SCHEDULER_DEFAULTS)
        # 允许蓝区覆盖 Main/Gems 等日常开关，但活动相关一律强制关
        for k, v in scheduler.items():
            if k in _EVENT_RELATED_FORCE_OFF:
                continue
            base[str(k)] = bool(v)
        for k in _EVENT_RELATED_FORCE_OFF:
            base[k] = False
        scheduler = base
        campaigns = {}
        gacha = {}
        event_format = 'NONE'
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

    result = MaterializeResult(device_id=device_id, date=date_str, blue=blue if isinstance(blue, dict) else {}, dry_run=dry_run)

    # 无任何象限时仍按「无活动」落盘清理，避免共斗/活动检测残留一直开着
    if not blue and not (isinstance(yellow, dict) and yellow) and not (isinstance(green, dict) and green):
        result.details.append('no server quadrant payload — treat as mode=none teardown')

    path = filepath_config(device_id)
    data = read_file(path)
    if not isinstance(data, dict):
        result.errors.append(f'config missing: {path}')
        return result

    proalas_backup = deep_get(data, ['ProalasData'], None)
    blue_patches = build_patches_from_blue(blue or {})
    yellow_sched = dict(yellow.get('scheduler_enable') or {}) if isinstance(yellow, dict) else {}
    merged_sched = merge_scheduler_maps(yellow_sched, blue_patches.get('scheduler_enable') or {})

    mode = str(blue_patches.get('mode', 'none'))
    no_event = mode == 'none' or not _blue_is_event_payload(blue or {})

    if no_event:
        # 黄区合并后再次强制关掉活动相关，防止黄区误带 Event=true
        for k in _EVENT_RELATED_FORCE_OFF:
            merged_sched[k] = False
        pref = str(deep_get(data, ['ProalasData', 'ResourcePreference'], 'material') or 'material').lower().strip()
        if pref == 'gem':
            merged_sched = merge_scheduler_maps(merged_sched, _NONE_SCHEDULER_GEM)
            result.details.append('ResourcePreference=gem (GemsFarming on, Main off)')
        else:
            merged_sched.setdefault('Main', True)
            merged_sched.setdefault('Main2', True)
            merged_sched['GemsFarming'] = False
            result.details.append('ResourcePreference=material (Main on, GemsFarming off)')
        blue_patches['event_format'] = 'NONE'
        blue_patches['campaign_events'] = {}
        blue_patches['gacha'] = {}

    valid_ids = _load_valid_event_ids()
    if no_event:
        result.applied += _apply_none_campaign_reset(data, result.details)
    else:
        result.applied += _apply_campaign_events(
            data, blue_patches.get('campaign_events') or {}, result.details,
            valid_event_ids=valid_ids,
        )

    proalas_data = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas_data, dict):
        proalas_data = {}
    proalas_data['SkipEventPt'] = no_event
    deep_set(data, keys=['ProalasData'], value=proalas_data)
    if no_event:
        result.details.append('ProalasData.SkipEventPt=True')

    # 无活动日关掉 PT 采集开关；有活动日重新打开（与计划同步）
    _ensure_task_bucket(data, 'ProalasCollector')
    read_pt = not no_event
    cur_read_pt = deep_get(data, ['ProalasCollector', 'ReadEventPt'], None)
    if cur_read_pt is not read_pt:
        deep_set(data, keys=['ProalasCollector', 'ReadEventPt'], value=read_pt)
        result.details.append(f'ProalasCollector.ReadEventPt={read_pt}')
        result.applied += 1

    result.applied += _apply_scheduler_enable(data, merged_sched, result.details)
    result.applied += _apply_gacha_meta(data, blue_patches.get('gacha') or {}, result.details)
    if not no_event:
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
