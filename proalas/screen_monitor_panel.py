"""DAP ProAlas 截图监控卡片上下文（首屏 SSR + HTMX 刷新共用）。"""
from __future__ import annotations

from typing import Any

from proalas.device_screenshots import find_screen_monitor_shot, image_url_for_shot
from proalas.remote_control import quota_status


def screen_monitor_enabled(config: dict) -> bool:
    block = config.get("ProalasScreenMonitor")
    if not isinstance(block, dict):
        return False
    sched = block.get("Scheduler")
    if not isinstance(sched, dict):
        return False
    return bool(sched.get("Enable"))


def build_screen_monitor_context(
    device_id: str,
    app_config: dict,
    device_config: dict,
) -> dict[str, Any]:
    shot = find_screen_monitor_shot(device_id, app_config)
    image_url = ""
    shot_date = ""
    shot_source = ""
    if shot:
        image_url = image_url_for_shot(device_id, shot)
        image_url = f"{image_url}?t={int(shot.mtime)}"
        shot_date = shot.shot_label
        shot_source = shot.source
    remote_q = quota_status(app_config, device_id)
    return {
        "device_id": device_id,
        "image_url": image_url,
        "shot_date": shot_date,
        "shot_source": shot_source,
        "monitor_on": screen_monitor_enabled(device_config),
        "remote_quota": remote_q,
    }
