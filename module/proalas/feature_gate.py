# -*- coding: utf-8 -*-
"""
ProAlas 付费功能锁（Pro 套餐）。

PROALAS_FEATURE_LOCK_ENABLED=False：试用阶段全部开放；正式上线改为 True。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.config.deep import deep_get
from module.logger import logger

# 主开关：False = 全部功能开放（试用/收款前）；True = 按套餐锁定 Pro 功能
PROALAS_FEATURE_LOCK_ENABLED = False

# 侧栏隐藏：任务仍存在、Scheduler 仍跑，配置合并到「定时计划」页
MENU_HIDDEN_TASKS: frozenset[str] = frozenset({
    'ProalasActivitySync',
    'ProalasGachaCheck',
    'ProalasBoatMessage',
    'ProalasGetExpUseExp',
})

PLAN_RANK = {
    'normal': 0,
    'pro': 1,
    'pro_plus': 2,
}

PLAN_LABEL = {
    'normal': 'Normal',
    'pro': 'Pro',
    'pro_plus': 'Pro+',
}

# 仅 Pro / Pro+ 可用的任务（Normal 可见但锁定）
PRO_ONLY_TASKS: frozenset[str] = frozenset({
    'ProalasAiPlanner',
    'ProalasAutoBreak',
    'ProalasAutoEquip',
    'ProalasAutoEventShop',
    'ProalasAutoExpBook',
    'ProalasAutoFleetChange',
    'ProalasFleetStrength',
    'ProalasPlanCalendar',
    'ProalasGachaCheck',
    'ProalasSmartDispatch',
})

FEATURE_MIN_PLAN: dict[str, str] = {task: 'pro' for task in PRO_ONLY_TASKS}

TASK_DISPLAY_NAME: dict[str, str] = {
    'ProalasAiPlanner': 'AI 自动规划',
    'ProalasAutoBreak': '自动突破',
    'ProalasAutoEquip': '自动换装备和配置装备',
    'ProalasAutoEventShop': '活动 PT 商店',
    'ProalasAutoExpBook': '自动使用经验书',
    'ProalasAutoFleetChange': '自动更换队伍',
    'ProalasFleetStrength': '编队采集',
    'ProalasPlanCalendar': '计划表',
    'ProalasGachaCheck': 'UP 抽卡检测',
    'ProalasCollectionFill': '自动补齐图鉴',
    'ProalasEventFormatFix': '活动检测与自动修正',
    'ProalasSpecialEvent': '特殊活动处理',
    'ProalasSmartDispatch': '智能资源调度',
}


def is_pro_only_task(task_command: str) -> bool:
    return task_command in PRO_ONLY_TASKS


def _parse_expire_at(raw: Any) -> datetime | None:
    if raw is None or raw == '':
        return None
    if hasattr(raw, 'strftime'):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def get_effective_plan(config) -> str:
    """读取有效套餐；过期或未配置时视为 normal。"""
    data = config.data if hasattr(config, 'data') else config
    plan = str(
        deep_get(data, ['ProalasAccount', 'ProalasAccount', 'PlanType'], 'normal') or 'normal'
    ).strip().lower()
    if plan not in PLAN_RANK:
        plan = 'normal'

    expire_raw = deep_get(data, ['ProalasAccount', 'ProalasAccount', 'ExpireAt'], '')
    expire_at = _parse_expire_at(expire_raw)
    if expire_at is not None and datetime.now() > expire_at:
        return 'normal'
    return plan


def check_feature(config, task_command: str) -> tuple[bool, str]:
    """
    检查任务是否对当前设备解锁。
    返回 (allowed, reason)；allowed=False 时 reason 为面向用户的说明。
    """
    if not PROALAS_FEATURE_LOCK_ENABLED:
        return True, ''

    min_plan = FEATURE_MIN_PLAN.get(task_command)
    if not min_plan:
        return True, ''

    current = get_effective_plan(config)
    need_rank = PLAN_RANK.get(min_plan, 1)
    have_rank = PLAN_RANK.get(current, 0)
    if have_rank >= need_rank:
        return True, ''

    feature_name = TASK_DISPLAY_NAME.get(task_command, task_command)
    need_label = PLAN_LABEL.get(min_plan, min_plan)
    have_label = PLAN_LABEL.get(current, current)
    return False, (
        f'「{feature_name}」需要 {need_label} 套餐，当前为 {have_label}。'
        f'请在「账户管理」查看套餐或续费后使用。'
    )


def gate_task_or_skip(ui, task_command: str) -> bool:
    """
    在任务 run() 开头调用。若已锁定则记录日志、推迟调度并返回 True（应直接 return）。
    """
    allowed, reason = check_feature(ui.config, task_command)
    if allowed:
        return False

    logger.warning('ProAlas feature locked: %s — %s', task_command, reason)
    ui.config.task_delay(server_update=True)
    return True


from module.proalas.log_scrub import install_proalas_coord_scrub

install_proalas_coord_scrub()
