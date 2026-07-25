"""停止运行窗口与夜间批处理时段冲突校验（无文件锁，纯规则）。"""
from __future__ import annotations

import re
from typing import Any

# 与 config.mumu_device.NightlyBatchReservedHours 默认一致
DEFAULT_RESERVED = (2, 3)


def _parse_hhmm(s: str) -> tuple[int, int] | None:
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(s).strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h == 24 and mi == 0:
        return 24, 0
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return h, mi
    return None


def _to_minutes(h: int, mi: int) -> int:
    if h == 24 and mi == 0:
        return 24 * 60
    return h * 60 + mi


def time_range_overlaps_reserved(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    reserved_start_hour: int = DEFAULT_RESERVED[0],
    reserved_end_hour: int = DEFAULT_RESERVED[1],
) -> bool:
    """判断 [start, end) 是否与 [reserved_start_hour:00, reserved_end_hour:00) 相交。"""
    rs = reserved_start_hour * 60
    re_ = reserved_end_hour * 60
    s = _to_minutes(*start)
    e = _to_minutes(*end)
    if s <= e:
        return s < re_ and e > rs
    return s < re_ or e > rs


def stop_time_overlaps_nightly_batch(
    payload: list[Any],
    *,
    reserved_start_hour: int = DEFAULT_RESERVED[0],
    reserved_end_hour: int = DEFAULT_RESERVED[1],
) -> bool:
    """payload 形如 ['true','18:00','24:00',['everyday']]。"""
    if not payload or len(payload) < 3:
        return False
    head = payload[0]
    if isinstance(head, str) and head.strip().lower() not in ("true", "1", "yes", "on"):
        if not isinstance(head, bool) or not head:
            return False
    elif isinstance(head, bool) and not head:
        return False
    start = _parse_hhmm(str(payload[1]))
    end = _parse_hhmm(str(payload[2]))
    if not start or not end:
        return False
    return time_range_overlaps_reserved(
        start,
        end,
        reserved_start_hour=reserved_start_hour,
        reserved_end_hour=reserved_end_hour,
    )


def stop_time_reject_reason(payload: list[Any]) -> str | None:
    if stop_time_overlaps_nightly_batch(payload):
        return (
            "停止运行时段不能与系统夜间批处理窗口重叠（默认 02:00–03:00）。"
            "请调整暂停时间，或联系管理员修改 NightlyBatchReservedHours。"
        )
    return None
