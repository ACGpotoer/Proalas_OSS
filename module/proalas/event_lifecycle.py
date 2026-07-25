# -*- coding: utf-8 -*-
"""
活动期任务生命周期（MMDD-MMDD）。

仅开发者改 TASK_LIFECYCLE / argument.yaml 后随更新推送；
用户可见但不可改。窗口外强制关闭 Scheduler.Enable，且禁止再打开。

开源版仅包含 ProalasSpecialEvent（竞拍场）；不含七日奖励 / 通用活动剧情。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from module.config.deep import deep_get, deep_set
from module.logger import logger

# 开发者改这里（并同步 argument/override 的 Lifecycle 默认值）后推送
TASK_LIFECYCLE: dict[str, str] = {
    'ProalasSpecialEvent': '0723-0730',
}

# 用户不可改的字段：每次读配置时写回开发者值
TASK_LOCKED_FIELDS: dict[str, dict[str, Any]] = {
    'ProalasSpecialEvent': {
        'EventName': 'Auction',
        'Lifecycle': '0723-0730',
    },
}

LIFECYCLE_TASKS: frozenset[str] = frozenset(TASK_LIFECYCLE.keys())


def parse_lifecycle_window(raw: str) -> Optional[tuple[tuple[int, int], tuple[int, int]]]:
    """
    Parse ``MMDD-MMDD`` → ((start_m, start_d), (end_m, end_d)).
    """
    text = str(raw or '').strip().replace('/', '').replace('.', '')
    if '-' not in text:
        return None
    left, right = text.split('-', 1)
    left, right = left.strip(), right.strip()
    if len(left) != 4 or len(right) != 4 or not left.isdigit() or not right.isdigit():
        return None
    sm, sd = int(left[:2]), int(left[2:])
    em, ed = int(right[:2]), int(right[2:])
    if not (1 <= sm <= 12 and 1 <= em <= 12 and 1 <= sd <= 31 and 1 <= ed <= 31):
        return None
    return (sm, sd), (em, ed)


def is_in_lifecycle(window: str, now: Optional[datetime | date] = None) -> bool:
    parsed = parse_lifecycle_window(window)
    if parsed is None:
        return False
    (sm, sd), (em, ed) = parsed
    if now is None:
        today = date.today()
    elif isinstance(now, datetime):
        today = now.date()
    else:
        today = now
    start_key = sm * 100 + sd
    end_key = em * 100 + ed
    today_key = today.month * 100 + today.day
    if start_key <= end_key:
        return start_key <= today_key <= end_key
    # 跨年：如 1220-0105
    return today_key >= start_key or today_key <= end_key


def task_lifecycle_window(task: str) -> str:
    return TASK_LIFECYCLE.get(task, '')


def is_task_in_lifecycle(task: str, now: Optional[datetime | date] = None) -> bool:
    return is_in_lifecycle(task_lifecycle_window(task), now=now)


def normalize_lifecycle_tasks(data: dict) -> None:
    """读配置时：写回锁定字段；窗口外强制关总开关；同步 Scheduler.Enable。"""
    for task, fields in TASK_LOCKED_FIELDS.items():
        group = deep_get(data, keys=task, default=None)
        if not isinstance(group, dict):
            continue
        for arg, value in fields.items():
            deep_set(data, keys=f'{task}.{task}.{arg}', value=value)
        in_window = is_task_in_lifecycle(task)
        nested_enable = bool(deep_get(data, keys=f'{task}.{task}.Enable', default=False))
        if not in_window:
            if nested_enable or deep_get(data, keys=f'{task}.Scheduler.Enable', default=False):
                logger.info('Lifecycle expired → force off %s', task)
            deep_set(data, keys=f'{task}.{task}.Enable', value=False)
            deep_set(data, keys=f'{task}.Scheduler.Enable', value=False)
        else:
            # 总开关驱动调度入队
            deep_set(data, keys=f'{task}.Scheduler.Enable', value=nested_enable)


def enforce_enable_or_false(task: str, want_enable: Any) -> bool:
    """用户试图打开总开关时：窗口外一律 False。"""
    if not want_enable:
        return False
    if task not in LIFECYCLE_TASKS:
        return bool(want_enable)
    if is_task_in_lifecycle(task):
        return True
    logger.warning('%s outside lifecycle %s — Enable forced off', task, task_lifecycle_window(task))
    return False


def guard_task_or_delay(config, task: str) -> bool:
    """
    任务入口守卫。

    Returns:
        True: 仍在生命周期且总开关已开，可继续业务
        False: 已关 / 已过期并推迟，调用方应 return
    """
    window = task_lifecycle_window(task)
    if not is_in_lifecycle(window):
        config.cross_set(f'{task}.{task}.Enable', False)
        config.cross_set(f'{task}.Scheduler.Enable', False)
        logger.info('%s lifecycle %s expired — disabled until next update', task, window)
        config.task_delay(server_update=True)
        return False
    nested = bool(config.cross_get(f'{task}.{task}.Enable', default=False))
    if not nested:
        config.cross_set(f'{task}.Scheduler.Enable', False)
        config.task_delay(server_update=True)
        return False
    config.cross_set(f'{task}.Scheduler.Enable', True)
    return True
