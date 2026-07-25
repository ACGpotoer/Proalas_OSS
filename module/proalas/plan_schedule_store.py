# -*- coding: utf-8 -*-
"""计划表持久化：config/proalas/PlanSchedule.json（按设备分桶，供 AI / WebUI 接口读写）。"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Optional

from module.config.utils import read_file, write_file
from module.logger import logger

from module.proalas.data_paths import PLAN_SCHEDULE_NAME, migrate_proalas_data_files, proalas_data_path

PLAN_VERSION = 2


def plan_path() -> str:
    migrate_proalas_data_files()
    return proalas_data_path(PLAN_SCHEDULE_NAME)


def load_plan_file() -> dict[str, Any]:
    raw = read_file(plan_path())
    if not isinstance(raw, dict):
        return {'version': PLAN_VERSION, 'devices': {}}
    if not isinstance(raw.get('devices'), dict):
        raw['devices'] = {}
    raw.setdefault('version', PLAN_VERSION)
    return raw


def save_plan_file(data: dict[str, Any]) -> None:
    path = plan_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    data['version'] = PLAN_VERSION
    data['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    write_file(path, data)
    logger.info('PlanSchedule saved %s', path)


def _device_bucket(data: dict[str, Any], device_id: str, *, create: bool = True) -> dict[str, Any]:
    devices = data.setdefault('devices', {})
    if not isinstance(devices, dict):
        devices = {}
        data['devices'] = devices
    key = str(device_id)
    bucket = devices.get(key)
    if not isinstance(bucket, dict):
        if not create:
            return {}
        bucket = {'entries': []}
        devices[key] = bucket
    if not isinstance(bucket.get('entries'), list):
        bucket['entries'] = []
    if not isinstance(bucket.get('overrides'), dict):
        bucket['overrides'] = {}
    return bucket


def get_device_day_override(device_id: str, date_str: str) -> dict[str, Any]:
    """设备层某日四色 override（覆盖全局日历同象限字段）。"""
    data = load_plan_file()
    bucket = _device_bucket(data, device_id, create=False)
    if not bucket:
        return {}
    overrides = bucket.get('overrides') or {}
    if not isinstance(overrides, dict):
        return {}
    row = overrides.get(str(date_str))
    return dict(row) if isinstance(row, dict) else {}


def upsert_device_day_override(
    device_id: str,
    date_str: str,
    payload: dict[str, Any],
    *,
    source: str = 'manual',
) -> dict[str, Any]:
    from module.proalas.quadrant_policy import validate_override_quadrants

    errors = validate_override_quadrants(payload, source=source)
    if errors:
        raise ValueError('; '.join(errors))
    data = load_plan_file()
    bucket = _device_bucket(data, device_id)
    overrides = bucket.setdefault('overrides', {})
    if not isinstance(overrides, dict):
        overrides = {}
        bucket['overrides'] = overrides
    key = str(date_str).strip()
    if not key:
        raise ValueError('date 必填，格式 YYYY-MM-DD')
    row = dict(overrides.get(key) or {})
    for quadrant, block in (payload or {}).items():
        if not isinstance(block, dict):
            continue
        existing = row.get(quadrant) if isinstance(row.get(quadrant), dict) else {}
        merged = dict(existing)
        merged.update(block)
        row[str(quadrant)] = merged
    overrides[key] = row
    save_plan_file(data)
    return row


def list_entries(device_id: str) -> list[dict[str, Any]]:
    data = load_plan_file()
    bucket = _device_bucket(data, device_id, create=False)
    entries = bucket.get('entries') if bucket else []
    return list(entries) if isinstance(entries, list) else []


def list_entries_in_month(device_id: str, year: int, month: int) -> list[dict[str, Any]]:
    prefix = f'{int(year):04d}-{int(month):02d}-'
    return [e for e in list_entries(device_id) if str(e.get('date', '')).startswith(prefix)]


def get_entry(device_id: str, entry_id: str) -> Optional[dict[str, Any]]:
    for row in list_entries(device_id):
        if str(row.get('id')) == str(entry_id):
            return dict(row)
    return None


def upsert_entry(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = load_plan_file()
    bucket = _device_bucket(data, device_id)
    entries: list[dict[str, Any]] = bucket['entries']
    entry_id = str(payload.get('id') or '').strip() or uuid.uuid4().hex
    now = datetime.now().isoformat(timespec='seconds')
    row = {
        'id': entry_id,
        'date': str(payload.get('date') or '').strip(),
        'start': str(payload.get('start') or '').strip(),
        'end': str(payload.get('end') or '').strip(),
        'action': str(payload.get('action') or 'run').strip(),
        'note': str(payload.get('note') or '').strip(),
        'source': str(payload.get('source') or 'manual').strip(),
        'updatedAt': now,
    }
    if not row['date']:
        raise ValueError('date 必填，格式 YYYY-MM-DD')
    replaced = False
    for i, old in enumerate(entries):
        if str(old.get('id')) == entry_id:
            row['createdAt'] = old.get('createdAt') or now
            entries[i] = row
            replaced = True
            break
    if not replaced:
        row['createdAt'] = now
        entries.append(row)
    bucket['entries'] = sorted(entries, key=lambda x: (x.get('date', ''), x.get('start', '')))
    save_plan_file(data)
    return row


def delete_entry(device_id: str, entry_id: str) -> bool:
    data = load_plan_file()
    bucket = _device_bucket(data, device_id, create=False)
    if not bucket:
        return False
    entries = bucket.get('entries') or []
    new_entries = [e for e in entries if str(e.get('id')) != str(entry_id)]
    if len(new_entries) == len(entries):
        return False
    bucket['entries'] = new_entries
    save_plan_file(data)
    return True
