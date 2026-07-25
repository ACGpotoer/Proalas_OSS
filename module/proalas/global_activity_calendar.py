# -*- coding: utf-8 -*-
"""全局活动日历：config/proalas/GlobalActivityCalendar.json（v3 tags+schedules，兼容 v2 days）。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from module.config.utils import read_file, write_file
from module.logger import logger
from module.proalas.calendar_schedule_resolver import resolve_global_day_from_calendar

GLOBAL_CALENDAR_VERSION = 3
from module.proalas.data_paths import (
    GLOBAL_CALENDAR_NAME,
    MANIFEST_NAME,
    migrate_proalas_data_files,
    proalas_data_path,
)

QUADRANT_KEYS = ('yellow', 'red', 'green', 'blue')


def calendar_path() -> str:
    migrate_proalas_data_files()
    return proalas_data_path(GLOBAL_CALENDAR_NAME)


def manifest_path() -> str:
    migrate_proalas_data_files()
    return proalas_data_path(MANIFEST_NAME)


def load_global_calendar() -> dict[str, Any]:
    raw = read_file(calendar_path())
    if not isinstance(raw, dict):
        return {'version': GLOBAL_CALENDAR_VERSION, 'tags': {}, 'schedules': [], 'days': {}}
    version = int(raw.get('version') or 2)
    if version >= 3:
        if not isinstance(raw.get('tags'), dict):
            raw['tags'] = {}
        if not isinstance(raw.get('schedules'), list):
            raw['schedules'] = []
    if not isinstance(raw.get('days'), dict):
        raw['days'] = {}
    raw.setdefault('version', version)
    return raw


def save_global_calendar(data: dict[str, Any]) -> None:
    path = calendar_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    data['version'] = int(data.get('version') or GLOBAL_CALENDAR_VERSION)
    data['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    write_file(path, data)
    logger.info('GlobalActivityCalendar saved %s', path)


def get_global_day(date_str: str) -> dict[str, Any]:
    """返回某日四色 dict（v3 经 resolver；v2 为 days 直读）。"""
    calendar = load_global_calendar()
    version = int(calendar.get('version') or 2)
    if version >= 3:
        return resolve_global_day_from_calendar(calendar, date_str)
    days = calendar.get('days') or {}
    row = days.get(str(date_str))
    return dict(row) if isinstance(row, dict) else {}


def get_global_quadrant(date_str: str, quadrant: str) -> dict[str, Any]:
    day = get_global_day(date_str)
    if isinstance(day.get(str(quadrant)), dict):
        return dict(day[str(quadrant)])
    block = day.get(str(quadrant))
    return dict(block) if isinstance(block, dict) else {}


def load_activity_manifest() -> dict[str, Any]:
    raw = read_file(manifest_path())
    return raw if isinstance(raw, dict) else {}


def manifest_server_key(server: str = 'cn') -> str:
    mapping = {
        'cn': 'cn_android',
        'en': 'en',
        'jp': 'jp',
        'tw': 'cn_ios',
    }
    return mapping.get(str(server or 'cn').lower(), 'cn_android')


def manifest_to_blue_block(server_entry: dict[str, Any]) -> dict[str, Any]:
    """B111 manifest 单服条目 → 蓝色象限 payload（降级用）。"""
    if not isinstance(server_entry, dict):
        return {}
    mode = str(server_entry.get('mode') or 'none').lower()
    block: dict[str, Any] = {
        'mode': mode,
        'source': 'manifest',
    }
    if server_entry.get('campaign_events'):
        block['campaign_events'] = dict(server_entry['campaign_events'])
    if server_entry.get('scheduler_enable'):
        block['scheduler_enable'] = dict(server_entry['scheduler_enable'])
    up = server_entry.get('now_gacha_pool') or []
    if up:
        block['gacha'] = {
            'up_ships': [str(x).strip() for x in up if str(x).strip()],
            'stop_if_owned': True,
        }
    farm = server_entry.get('farm_ships') or []
    if farm:
        block['farm_ships'] = [str(x).strip() for x in farm if str(x).strip()]
    return block


def resolve_manifest_blue(server: str = 'cn') -> Optional[dict[str, Any]]:
    manifest = load_activity_manifest()
    servers = manifest.get('servers') or {}
    if not isinstance(servers, dict):
        return None
    key = manifest_server_key(server)
    entry = servers.get(key)
    if not isinstance(entry, dict):
        return None
    valid_until = entry.get('valid_until')
    if valid_until:
        try:
            text = str(valid_until).replace('Z', '+00:00')[:19]
            expire = datetime.fromisoformat(text)
            if datetime.now() > expire:
                logger.info('activity_manifest %s expired at %s', key, valid_until)
                return manifest_to_blue_block({'mode': 'none', 'scheduler_enable': entry.get('scheduler_enable') or {}})
        except ValueError:
            pass
    return manifest_to_blue_block(entry)
