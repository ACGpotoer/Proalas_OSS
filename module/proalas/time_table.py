# -*- coding: utf-8 -*-
"""读写 mumucontrol/TimeTable.json，供 HostAgent 与 WebUI 只读展示消费。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from module.config.utils import read_file, write_file
from module.logger import logger

TIMETABLE_VERSION = 1

# 运行时数据在 mumucontrol/，避免出现在 WebUI config 目录
def timetable_path() -> str:
    """开源版不依赖 mumucontrol；优先本地 dap_data / config/proalas。"""
    try:
        from mumucontrol.paths import migrate_legacy_runtime_files, timetable_path as _mmc_tt_path

        migrate_legacy_runtime_files()
        return _mmc_tt_path()
    except Exception:
        pass
    root = os.path.abspath('.')
    for rel in (
        os.path.join('dap_data', 'TimeTable.json'),
        os.path.join('config', 'proalas', 'TimeTable.json'),
        os.path.join('mumucontrol', 'runtime', 'TimeTable.json'),
    ):
        path = os.path.join(root, rel)
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        return path
    return os.path.join(root, 'dap_data', 'TimeTable.json')


# 定时计划任务自身及纯 WebUI 任务默认不参与「最早 NextRun」统计
DEFAULT_EXCLUDE_COMMANDS = frozenset({
    'ProalasTimerPlan',
    'ProalasPlanCalendar',
    'ProalasActivitySync',
    'ProalasGachaCheck',
    'ProalasAiPlanner',
    'ProalasResourceStats',
    'ProalasSmartDispatch',
    'ProalasAutoFleetChange',
    'ProalasAccount',
    'ProalasScreenMonitor',
})


def _parse_next_run(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        text = value.strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def load_timetable() -> dict[str, Any]:
    path = timetable_path()
    raw = read_file(path)
    if not isinstance(raw, dict):
        return {'version': TIMETABLE_VERSION, 'devices': {}}
    if 'devices' not in raw or not isinstance(raw.get('devices'), dict):
        raw['devices'] = {}
    raw.setdefault('version', TIMETABLE_VERSION)
    return raw


def save_timetable(data: dict[str, Any]) -> None:
    path = timetable_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    data['version'] = TIMETABLE_VERSION
    data['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    write_file(path, data)
    logger.info('TimeTable saved %s devices=%s', path, len(data.get('devices') or {}))


def scan_enabled_tasks(
    config_data: dict[str, Any],
    *,
    exclude_commands: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """扫描 config 内所有 Scheduler.Enable=true 的任务。"""
    skip = set(DEFAULT_EXCLUDE_COMMANDS)
    if exclude_commands:
        skip |= {str(x).strip() for x in exclude_commands if str(x).strip()}
    out: list[dict[str, Any]] = []
    for task_name, body in (config_data or {}).items():
        if not isinstance(body, dict):
            continue
        sched = body.get('Scheduler')
        if not isinstance(sched, dict):
            continue
        if not sched.get('Enable'):
            continue
        command = str(sched.get('Command') or task_name).strip()
        if command in skip or task_name in skip:
            continue
        next_run = _parse_next_run(sched.get('NextRun'))
        if next_run is None:
            continue
        out.append({
            'taskName': str(task_name),
            'command': command,
            'nextRun': next_run,
        })
    return out


def build_device_snapshot(
    config_name: str,
    config_data: dict[str, Any],
    *,
    exclude_commands: Optional[set[str]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    计算单设备快照。

    needRunning / status:
      - 任一已启用任务 NextRun <= now → true（有待运行）
      - 否则若最早 NextRun > now → false（当前可关 MuMu）
      - 无启用任务 → false
    """
    now = (now or datetime.now()).replace(microsecond=0)
    tasks = scan_enabled_tasks(config_data, exclude_commands=exclude_commands)
    pending = [t for t in tasks if t['nextRun'] <= now]
    need_running = bool(pending)

    earliest_command = ''
    earliest_next_run: Optional[datetime] = None
    if tasks:
        earliest = min(tasks, key=lambda x: x['nextRun'])
        earliest_command = str(earliest['command'])
        earliest_next_run = earliest['nextRun']
        if not need_running and earliest_next_run > now:
            need_running = False
        elif earliest_next_run <= now:
            need_running = True

    return {
        'configName': str(config_name),
        'updatedAt': now.isoformat(timespec='seconds'),
        'needRunning': bool(need_running),
        'status': bool(need_running),
        'earliestCommand': earliest_command,
        'earliestNextRun': earliest_next_run.strftime('%Y-%m-%d %H:%M:%S') if earliest_next_run else '',
        'pendingCommands': [t['command'] for t in sorted(pending, key=lambda x: x['nextRun'])],
        'enabledTaskCount': len(tasks),
        'waitingCommands': [
            {
                'command': t['command'],
                'nextRun': t['nextRun'].strftime('%Y-%m-%d %H:%M:%S'),
            }
            for t in sorted(tasks, key=lambda x: x['nextRun'])
        ],
    }


def update_device_timetable(
    config_name: str,
    config_data: dict[str, Any],
    *,
    exclude_commands: Optional[set[str]] = None,
) -> dict[str, Any]:
    snap = build_device_snapshot(
        config_name,
        config_data,
        exclude_commands=exclude_commands,
    )
    data = load_timetable()
    devices = data.setdefault('devices', {})
    if not isinstance(devices, dict):
        devices = {}
        data['devices'] = devices
    devices[str(config_name)] = snap
    save_timetable(data)
    logger.info(
        'TimeTable[%s] needRunning=%s earliest=%s @ %s pending=%s',
        config_name,
        snap['needRunning'],
        snap['earliestCommand'],
        snap['earliestNextRun'],
        snap['pendingCommands'],
    )
    return snap


def read_device_timetable(config_name: str) -> dict[str, Any]:
    data = load_timetable()
    devices = data.get('devices') or {}
    row = devices.get(str(config_name)) if isinstance(devices, dict) else None
    return dict(row) if isinstance(row, dict) else {}
