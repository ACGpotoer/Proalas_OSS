"""从 config/{device}.json 汇总 ProAlas 任务 Scheduler（DAP 只读）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

PROALAS_TASK_LABELS: dict[str, str] = {
    "ProalasAutoBreak": "自动突破",
    "ProalasAutoEquip": "自动换装备",
    "ProalasAutoEventShop": "活动商店",
    "ProalasAutoFleetChange": "自动换队",
    "ProalasCollector": "ProAlas 采集",
    "ProalasFleetStrength": "编队实力",
    "ProalasResourceStats": "资源统计",
    "ProalasSmartDispatch": "智能调度",
    "ProalasScreenMonitor": "截图监控",
    "ProalasTimerPlan": "定时计划",
    "ProalasPlanCalendar": "计划表",
    "ProalasActivitySync": "活动同步",
    "ProalasGachaCheck": "UP 抽卡检测",
    "ProalasAiPlanner": "AI 自动规划",
    "ProalasAccount": "账户管理",
    "ProalasBoatMessage": "船坞消息",
    "ProalasGetExpUseExp": "演习经验",
}

PROALAS_TASK_ORDER: tuple[str, ...] = tuple(PROALAS_TASK_LABELS.keys())


def _parse_next_run(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value).strip()


def list_proalas_schedulers(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_name in PROALAS_TASK_ORDER:
        body = config.get(task_name)
        if not isinstance(body, dict):
            continue
        sched = body.get("Scheduler")
        if not isinstance(sched, dict):
            continue
        command = str(sched.get("Command") or task_name).strip()
        rows.append(
            {
                "task": task_name,
                "label": PROALAS_TASK_LABELS.get(task_name, task_name),
                "command": command,
                "enable": bool(sched.get("Enable")),
                "next_run": _parse_next_run(sched.get("NextRun")),
                "success_interval": sched.get("SuccessInterval"),
                "failure_interval": sched.get("FailureInterval"),
            }
        )
    # 其它 Proalas* 键（未来扩展）
    for task_name, body in sorted(config.items()):
        if not str(task_name).startswith("Proalas"):
            continue
        if task_name in PROALAS_TASK_LABELS:
            continue
        if not isinstance(body, dict):
            continue
        sched = body.get("Scheduler")
        if not isinstance(sched, dict):
            continue
        rows.append(
            {
                "task": task_name,
                "label": PROALAS_TASK_LABELS.get(task_name, task_name),
                "command": str(sched.get("Command") or task_name).strip(),
                "enable": bool(sched.get("Enable")),
                "next_run": _parse_next_run(sched.get("NextRun")),
                "success_interval": sched.get("SuccessInterval"),
                "failure_interval": sched.get("FailureInterval"),
            }
        )
    return rows


def build_timer_plan_summary(
    config: dict[str, Any],
    *,
    timetable_snap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """定时计划只读摘要：ExtraExclude + 启用任务 NextRun + TimeTable 快照。"""
    timer_body = config.get("ProalasTimerPlan")
    extra_exclude: list[str] = []
    if isinstance(timer_body, dict):
        tp = timer_body.get("ProalasTimerPlan")
        if isinstance(tp, dict) and tp.get("ExtraExclude"):
            raw = tp.get("ExtraExclude")
            if isinstance(raw, list):
                extra_exclude = [str(x) for x in raw]
            elif isinstance(raw, str) and raw.strip():
                extra_exclude = [raw.strip()]

    enabled = [
        r for r in list_proalas_schedulers(config)
        if r["enable"] and r["next_run"]
    ]
    waiting = sorted(enabled, key=lambda x: x["next_run"])

    snap = timetable_snap or {}
    return {
        "extra_exclude": extra_exclude,
        "enabled_count": len(enabled),
        "waiting": waiting[:12],
        "need_running": bool(snap.get("needRunning")),
        "earliest_command": str(snap.get("earliestCommand") or ""),
        "earliest_next_run": str(snap.get("earliestNextRun") or ""),
        "pending_commands": snap.get("pendingCommands") or [],
        "timetable_updated": str(snap.get("updatedAt") or ""),
        "has_timetable": bool(snap),
    }
