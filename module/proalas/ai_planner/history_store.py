# -*- coding: utf-8
"""AI 规划历史：config/proalas/AiPlannerHistory.json。"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Optional

from module.config.utils import read_file, write_file
from module.logger import logger

from module.proalas.data_paths import (
    AI_PLANNER_CACHE_NAME,
    AI_PLANNER_HISTORY_NAME,
    migrate_proalas_data_files,
    proalas_data_path,
)


HISTORY_VERSION = 1


def _history_path() -> str:
    migrate_proalas_data_files()
    return proalas_data_path(AI_PLANNER_HISTORY_NAME)


def _cache_path() -> str:
    migrate_proalas_data_files()
    return proalas_data_path(AI_PLANNER_CACHE_NAME)


def load_history_file() -> dict[str, Any]:
    raw = read_file(_history_path())
    if not isinstance(raw, dict):
        return {'version': HISTORY_VERSION, 'devices': {}}
    if not isinstance(raw.get('devices'), dict):
        raw['devices'] = {}
    raw.setdefault('version', HISTORY_VERSION)
    return raw


def save_history_file(data: dict[str, Any]) -> None:
    path = _history_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    data['version'] = HISTORY_VERSION
    data['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    write_file(path, data)
    logger.info('AiPlannerHistory saved %s', path)


def list_history(device_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    data = load_history_file()
    bucket = (data.get('devices') or {}).get(str(device_id)) or {}
    rows = bucket.get('runs') if isinstance(bucket, dict) else []
    if not isinstance(rows, list):
        return []
    return list(reversed(rows[-limit:]))


def append_history(
    device_id: str,
    *,
    summary: str,
    commands: list[dict[str, Any]],
    applied: bool,
    warnings: Optional[list[str]] = None,
    mode: str = 'preview',
    strategy: str = '',
) -> dict[str, Any]:
    data = load_history_file()
    devices = data.setdefault('devices', {})
    bucket = devices.setdefault(str(device_id), {'runs': []})
    runs = bucket.setdefault('runs', [])
    row = {
        'id': uuid.uuid4().hex,
        'at': datetime.now().isoformat(timespec='seconds'),
        'summary': str(summary or ''),
        'commandCount': len(commands),
        'commands': commands,
        'applied': bool(applied),
        'mode': mode,
        'warnings': list(warnings or []),
        'strategy': str(strategy or ''),
    }
    runs.append(row)
    if len(runs) > 100:
        bucket['runs'] = runs[-100:]
    save_history_file(data)
    return row


def save_session_cache(device_id: str, payload: dict[str, Any]) -> None:
    path = _cache_path()
    raw = read_file(path)
    if not isinstance(raw, dict):
        raw = {'devices': {}}
    devices = raw.setdefault('devices', {})
    devices[str(device_id)] = {
        'updatedAt': datetime.now().isoformat(timespec='seconds'),
        **payload,
    }
    write_file(path, raw)


def load_session_cache(device_id: str) -> dict[str, Any]:
    raw = read_file(_cache_path())
    if not isinstance(raw, dict):
        return {}
    bucket = (raw.get('devices') or {}).get(str(device_id))
    return dict(bucket) if isinstance(bucket, dict) else {}
