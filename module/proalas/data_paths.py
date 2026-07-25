# -*- coding: utf-8 -*-
"""ProAlas 内部数据文件：统一放在 config/proalas/，避免 WebUI 侧栏列出。"""
from __future__ import annotations

import os
import shutil
from typing import Optional

from module.logger import logger

PROALAS_DATA_DIR = './config/proalas'

GLOBAL_CALENDAR_NAME = 'GlobalActivityCalendar.json'
GLOBAL_CALENDAR_EXAMPLE_NAME = 'GlobalActivityCalendar.example.json'
MANIFEST_NAME = 'activity_manifest.json'
PLAN_SCHEDULE_NAME = 'PlanSchedule.json'
AI_PLANNER_HISTORY_NAME = 'AiPlannerHistory.json'
AI_PLANNER_CACHE_NAME = 'AiPlannerCache.json'
ALAS_CONFIG_NAME = 'AlasConfig.json'

# config 根目录遗留名（alas_instance 亦跳过）
LEGACY_ROOT_JSON_NAMES = frozenset({
    'HostControl',
    'TimeTable',
    'AlasConfig',
    'AiPlannerCache',
    'AiPlannerHistory',
    'GlobalActivityCalendar',
    'GlobalActivityCalendar.example',
    'PlanSchedule',
    'activity_manifest',
})

_MIGRATED = False


def proalas_data_dir(*, create: bool = True) -> str:
    path = os.path.normpath(PROALAS_DATA_DIR)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def proalas_data_path(filename: str, *, create_dir: bool = True) -> str:
    return os.path.normpath(os.path.join(proalas_data_dir(create=create_dir), filename))


def _move_legacy_file(src: str, dst: str) -> Optional[str]:
    src_n = os.path.normpath(src)
    dst_n = os.path.normpath(dst)
    if not os.path.isfile(src_n):
        return None
    if os.path.isfile(dst_n):
        try:
            os.remove(src_n)
            logger.info('ProAlas data: removed duplicate legacy %s (dest exists)', src_n)
            return f'removed duplicate {src_n}'
        except OSError as e:
            logger.warning('ProAlas data: could not remove legacy %s: %s', src_n, e)
            return None
    os.makedirs(os.path.dirname(dst_n) or '.', exist_ok=True)
    shutil.move(src_n, dst_n)
    logger.info('ProAlas data: migrated %s -> %s', src_n, dst_n)
    return f'{src_n} -> {dst_n}'


def migrate_proalas_data_files() -> list[str]:
    """首次访问时将 config/*.json 运维文件迁入 config/proalas/。"""
    global _MIGRATED
    if _MIGRATED:
        return []
    _MIGRATED = True
    moved: list[str] = []
    root = os.path.normpath('./config')
    dest_dir = proalas_data_dir()
    for name in (
        GLOBAL_CALENDAR_NAME,
        GLOBAL_CALENDAR_EXAMPLE_NAME,
        MANIFEST_NAME,
        PLAN_SCHEDULE_NAME,
        AI_PLANNER_HISTORY_NAME,
        AI_PLANNER_CACHE_NAME,
        ALAS_CONFIG_NAME,
    ):
        rep = _move_legacy_file(os.path.join(root, name), os.path.join(dest_dir, name))
        if rep:
            moved.append(rep)
    return moved
