# -*- coding: utf-8 -*-
"""T-HT 活动 Event / Event2 配置写入（仅 Campaign.Name，不写 Mode）。

约定：Event = T 线（t1–t3），Event2 = HT 线（ht1–ht3）；简单/困难由章节名区分。
"""
from __future__ import annotations

from typing import Any

MAP_ACH_PUSH = '100_percent_clear'
MAP_ACH_FARM = 'non_stop'

THT_EVENT_TASK = 'Event'
THT_EVENT2_TASK = 'Event2'
THT_NORMAL_STAGES = ('t1', 't2', 't3')
THT_HARD_STAGES = ('ht1', 'ht2', 'ht3')

DEFAULT_FLEET1 = 1
DEFAULT_FLEET2 = 2


def apply_task_stage(
    writer,
    task: str,
    stage: str,
    *,
    map_achievement: str,
    fleet1: int = DEFAULT_FLEET1,
    fleet2: int = DEFAULT_FLEET2,
    enable: bool = True,
) -> None:
    """写入单任务出击章节（不触碰 Campaign.Mode）。"""
    if enable:
        writer.cross_set(f'{task}.Campaign.Name', stage)
        writer.cross_set(f'{task}.Scheduler.Enable', True)
        writer.cross_set(f'{task}.StopCondition.MapAchievement', map_achievement)
        writer.cross_set(f'{task}.Fleet.Fleet1', int(fleet1))
        writer.cross_set(f'{task}.Fleet.Fleet2', int(fleet2))
    else:
        writer.cross_set(f'{task}.Scheduler.Enable', False)


def apply_tht_push_pair(
    writer,
    *,
    event_stage: str,
    event2_stage: str,
    map_achievement: str = MAP_ACH_PUSH,
) -> None:
    """推图期：Event 跑 T 关，Event2 跑 HT 关。"""
    apply_task_stage(writer, THT_EVENT_TASK, event_stage, map_achievement=map_achievement)
    apply_task_stage(writer, THT_EVENT2_TASK, event2_stage, map_achievement=map_achievement)


def apply_tht_farm_ht3(writer) -> None:
    """T 线已通（或全线已通）后：Event / Event2 均刷 ht3，成就停止 = 否。"""
    farm_stage = THT_HARD_STAGES[-1]
    apply_task_stage(writer, THT_EVENT_TASK, farm_stage, map_achievement=MAP_ACH_FARM)
    apply_task_stage(writer, THT_EVENT2_TASK, farm_stage, map_achievement=MAP_ACH_FARM)


def apply_tht_to_config_data(
    data: dict[str, Any],
    *,
    event_stage: str,
    event2_stage: str,
    map_achievement: str,
    event_enable: bool = True,
    event2_enable: bool = True,
) -> list[str]:
    """供编排器使用：直接改 config dict。"""
    from module.config.deep import deep_set

    details: list[str] = []
    for task, stage, enable in (
        (THT_EVENT_TASK, event_stage, event_enable),
        (THT_EVENT2_TASK, event2_stage, event2_enable),
    ):
        if task not in data or not isinstance(data.get(task), dict):
            data[task] = {}
        if enable:
            deep_set(data, keys=[task, 'Campaign', 'Name'], value=stage)
            deep_set(data, keys=[task, 'StopCondition', 'MapAchievement'], value=map_achievement)
            deep_set(data, keys=[task, 'Fleet', 'Fleet1'], value=DEFAULT_FLEET1)
            deep_set(data, keys=[task, 'Fleet', 'Fleet2'], value=DEFAULT_FLEET2)
            deep_set(data, keys=[task, 'Scheduler', 'Enable'], value=True)
            details.append(f'{task} Name={stage} MapAchievement={map_achievement}')
        else:
            deep_set(data, keys=[task, 'Scheduler', 'Enable'], value=False)
            details.append(f'{task}.Scheduler.Enable=false')
    return details
