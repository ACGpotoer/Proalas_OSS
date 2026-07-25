# -*- coding: utf-8 -*-
"""从 proalas_sync_gateway 拉取 GlobalActivityCalendar / PlanSchedule 到本机 config/proalas。"""
from __future__ import annotations

import copy
import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from module.logger import logger
from module.proalas.data_paths import GLOBAL_CALENDAR_NAME, PLAN_SCHEDULE_NAME, proalas_data_path

SERVER_QUADRANTS = frozenset({'yellow', 'green', 'blue'})


@dataclass
class SyncPullResult:
    ok: bool = True
    calendar_written: bool = False
    plan_schedule_written: bool = False
    calendar_tags: int = 0
    plan_devices: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


def _get_json(base: str, path: str, token: str, *, timeout: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(
        base.rstrip('/') + path,
        headers={'Authorization': f'Bearer {token}'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _backup_and_write(path: str, data: dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.isfile(path):
        bak = path + '.bak.' + datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(path, bak)
        logger.info('SyncGateway backup %s', bak)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    logger.info('SyncGateway written %s', path)


def merge_plan_schedule_server_quadrants(
    local: dict[str, Any],
    remote: dict[str, Any],
) -> dict[str, Any]:
    """
    合并计划表：云端仅黄/绿/蓝；本地红色（AI 规划）保留。
    """
    out = copy.deepcopy(local if isinstance(local, dict) else {})
    out.setdefault('version', int(remote.get('version') or out.get('version') or 2))
    local_devices = out.setdefault('devices', {})
    if not isinstance(local_devices, dict):
        local_devices = {}
        out['devices'] = local_devices
    remote_devices = remote.get('devices') or {}
    if not isinstance(remote_devices, dict):
        return out

    for device_id, remote_bucket in remote_devices.items():
        if not isinstance(remote_bucket, dict):
            continue
        bucket = local_devices.setdefault(str(device_id), {'entries': [], 'overrides': {}})
        if not isinstance(bucket.get('entries'), list):
            bucket['entries'] = []
        local_overrides = bucket.setdefault('overrides', {})
        if not isinstance(local_overrides, dict):
            local_overrides = {}
            bucket['overrides'] = local_overrides
        remote_overrides = remote_bucket.get('overrides') or {}
        if not isinstance(remote_overrides, dict):
            continue
        for date_str, remote_row in remote_overrides.items():
            if not isinstance(remote_row, dict):
                continue
            merged = dict(local_overrides.get(str(date_str)) or {})
            local_red = merged.get('red') if isinstance(merged.get('red'), dict) else None
            for q in SERVER_QUADRANTS:
                block = remote_row.get(q)
                if isinstance(block, dict) and block:
                    merged[q] = copy.deepcopy(block)
            if local_red:
                merged['red'] = local_red
            elif 'red' in remote_row:
                merged.pop('red', None)
            local_overrides[str(date_str)] = merged
    return out


def pull_from_sync_gateway(
    *,
    base_url: str,
    token: str,
    pull_plan_schedule: bool = True,
    merge_plan_with_local: bool = True,
) -> SyncPullResult:
    result = SyncPullResult()
    base = str(base_url or '').strip().rstrip('/')
    token = str(token or '').strip()
    if not base:
        result.ok = False
        result.errors.append('SyncGatewayUrl empty')
        return result
    if not token:
        result.ok = False
        result.errors.append('SyncGatewayToken empty')
        return result

    cal_path = proalas_data_path(GLOBAL_CALENDAR_NAME)
    plan_path = proalas_data_path(PLAN_SCHEDULE_NAME)

    try:
        cal_resp = _get_json(base, '/v1/global-calendar', token)
        calendar = cal_resp.get('calendar') or {}
        if not isinstance(calendar, dict):
            raise ValueError('invalid calendar payload')
        _backup_and_write(cal_path, calendar)
        result.calendar_written = True
        result.calendar_tags = len(calendar.get('tags') or {})
        result.details.append(
            f'calendar tags={result.calendar_tags} schedules={len(calendar.get("schedules") or [])}'
        )
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, json.JSONDecodeError) as e:
        result.ok = False
        result.errors.append(f'global-calendar: {e}')
        logger.error('SyncGateway calendar pull failed: %s', e)

    if pull_plan_schedule and result.ok:
        try:
            ps_resp = _get_json(base, '/v1/plan-schedule', token)
            remote_ps = ps_resp.get('planSchedule') or {}
            if not isinstance(remote_ps, dict):
                raise ValueError('invalid planSchedule payload')
            if merge_plan_with_local and os.path.isfile(plan_path):
                from module.config.utils import read_file

                local_ps = read_file(plan_path)
                if not isinstance(local_ps, dict):
                    local_ps = {'version': 2, 'devices': {}}
                merged = merge_plan_schedule_server_quadrants(local_ps, remote_ps)
            else:
                merged = remote_ps
            _backup_and_write(plan_path, merged)
            result.plan_schedule_written = True
            result.plan_devices = len(merged.get('devices') or {})
            result.details.append(f'planSchedule devices={result.plan_devices} (Y/G/B merged, red kept local)')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                result.details.append('plan-schedule: not on server, skip')
            else:
                result.ok = False
                result.errors.append(f'plan-schedule: {e}')
                logger.error('SyncGateway plan-schedule pull failed: %s', e)
        except (urllib.error.URLError, ValueError, json.JSONDecodeError) as e:
            result.ok = False
            result.errors.append(f'plan-schedule: {e}')
            logger.error('SyncGateway plan-schedule pull failed: %s', e)

    return result
