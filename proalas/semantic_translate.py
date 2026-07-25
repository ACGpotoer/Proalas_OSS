"""预提示词语义行 → change / userdata / 定时任务（对照 提示词及其路径对照键值.txt）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from proalas.semantic_parse import format_userdata_line

from proalas.stop_time_guard import stop_time_reject_reason

# 预提示词死配置（与 预提示词.txt 一致，上线后可改为读配置）
DEFAULT_EVENT_ID = "event_20260417_cn"
DEFAULT_EVENT_STAGE = "t2"

# Alas 模块前缀
_MAIN_MODULES = {
    "主线一": "Main",
    "主线二": "Main2",
    "主线三": "Main3",
}
_EVENT_MODULES = {
    "活动一": "Event",
    "活动二": "Event2",
}
_SPECIAL_MODULE = "CoalitionSp"
_RAID_MODULE = "Raid"
_GEMS_MODULE = "GemsFarming"

# 大世界子功能（对照表「大世界」段）
_OPSI_ENABLE_PATHS = [
    "OpsiAshBeacon.Scheduler.Enable",
    "OpsiAshAssist.Scheduler.Enable",
    "OpsiExplore.Scheduler.Enable",
    "OpsiShop.Scheduler.Enable",
    "OpsiVoucher.Scheduler.Enable",
    "OpsiDaily.Scheduler.Enable",
    "OpsiObscure.Scheduler.Enable",
    "OpsiAbyssal.Scheduler.Enable",
    "OpsiStronghold.Scheduler.Enable",
    "OpsiMonthBoss.Scheduler.Enable",
    "OpsiMeowfficerFarming.Scheduler.Enable",
    "OpsiHazard1Leveling.Scheduler.Enable",
]

_FLEET_ORDER: dict[tuple[str, str], str] = {
    ("z", "b"): "fleet1_mob_fleet2_boss",
    ("a", "n"): "fleet1_all_fleet2_standby",
}

# 语义指令名别名 → 规范名
_NAME_ALIASES: dict[str, str] = {
    "打开自动配队主线": "自动配队主线",
    "打开自动配队活动": "自动配队活动",
    "打开自动抽卡": "自动抽卡",
    "打开自动突破": "自动突破",
    "打开自动吃书": "自动吃书",
    "打开自动兑换商店": "自动兑换活动商店",
    "打开自动兑换活动商店": "自动兑换活动商店",
    "打开大世界全部功能": "大世界功能开",
    "关闭大世界全部功能": "大世界功能关",
    "大世界": "大世界功能开",
}

_FLEET_BRACKET = re.compile(
    r"^\[([^\]]+)\]([azan])\[([^\]]+)\]([zbn])$",
    re.I,
)
_FLEET_COMPACT = re.compile(r"^(\d)([azan])(\d)([zbn])$", re.I)


@dataclass
class TranslateResult:
    lines: list[str] = field(default_factory=list)
    scheduled: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _norm_name(name: str) -> str:
    n = name.strip()
    return _NAME_ALIASES.get(n, n)


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    return s in ("true", "1", "on", "yes", "开", "打开", "启用")


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _format_change(device_id: str, path: str, value: Any) -> str:
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        v = str(int(value)) if float(value) == int(value) else str(value)
    else:
        v = str(value)
    return f"change {device_id} {path} {v}"


def _parse_fleet_shorthand(raw: Any) -> tuple[int, int, str] | None:
    s = _as_str(raw).lower()
    if not s:
        return None
    m = _FLEET_BRACKET.match(s) or _FLEET_COMPACT.match(s)
    if not m:
        return None
    f1_s, m1, f2_s, m2 = m.group(1), m.group(2).lower(), m.group(3), m.group(4).lower()
    try:
        f1 = int(re.search(r"\d+", f1_s).group()) if re.search(r"\d+", f1_s) else int(f1_s)
        f2 = int(re.search(r"\d+", f2_s).group()) if re.search(r"\d+", f2_s) else int(f2_s)
    except (ValueError, AttributeError):
        return None
    order = _FLEET_ORDER.get((m1, m2))
    if order is None:
        return None
    if not (1 <= f1 <= 6 and 1 <= f2 <= 6 and f1 != f2):
        return None
    return f1, f2, order


def _emit_scheduler(
    out: list[str],
    device_id: str,
    module: str,
    enable: bool,
) -> None:
    out.append(_format_change(device_id, f"{module}.Scheduler.Enable", enable))


def _emit_campaign(
    out: list[str],
    device_id: str,
    module: str,
    *,
    enable: bool,
    name: str | None = None,
    mode: str | None = None,
    event: str | None = None,
    fleet: Any = None,
) -> None:
    _emit_scheduler(out, device_id, module, enable)
    if name:
        out.append(_format_change(device_id, f"{module}.Campaign.Name", name))
    if mode:
        out.append(_format_change(device_id, f"{module}.Campaign.Mode", mode))
    if event:
        out.append(_format_change(device_id, f"{module}.Campaign.Event", event))
    parsed = _parse_fleet_shorthand(fleet) if fleet else None
    if parsed:
        f1, f2, order = parsed
        out.append(_format_change(device_id, f"{module}.Fleet.Fleet1", f1))
        out.append(_format_change(device_id, f"{module}.Fleet.Fleet2", f2))
        out.append(_format_change(device_id, f"{module}.Fleet.FleetOrder", order))


def _payload_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    return [payload]


def _translate_main_event(
    device_id: str,
    module: str,
    payload: Any,
    *,
    default_name: str | None = None,
    default_mode: str = "normal",
    default_fleet: str | None = None,
    default_event: str | None = None,
    event_layout: bool = False,
) -> TranslateResult:
    """event_layout: 活动类 ['开','t2','6a1n']（无单独 mode 时第三项为配队）。"""
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    enable = _as_bool(pl[0])
    name: str | None = default_name
    mode: str | None = default_mode
    fleet: Any = default_fleet

    if len(pl) == 1:
        lines: list[str] = []
        _emit_scheduler(lines, device_id, module, enable)
        return TranslateResult(lines=lines)

    if event_layout:
        if len(pl) >= 4:
            name, mode, fleet = _as_str(pl[1]), _as_str(pl[2]), pl[3]
        elif len(pl) == 3:
            name, mode, fleet = _as_str(pl[1]), default_mode, pl[2]
        elif len(pl) == 2:
            name = _as_str(pl[1])
    else:
        if len(pl) >= 4:
            name, mode, fleet = _as_str(pl[1]), _as_str(pl[2]), pl[3]
        elif len(pl) == 3:
            name, mode = _as_str(pl[1]), _as_str(pl[2])
        elif len(pl) == 2:
            name = _as_str(pl[1])

    lines: list[str] = []
    _emit_campaign(
        lines,
        device_id,
        module,
        enable=enable,
        name=name or None,
        mode=mode or None,
        event=default_event,
        fleet=fleet,
    )
    return TranslateResult(lines=lines)


def _translate_raid(device_id: str, payload: Any) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    enable = _as_bool(pl[0])
    mode = _as_str(pl[1]) if len(pl) > 1 and pl[1] not in (None, "") else "normal"
    lines: list[str] = []
    _emit_scheduler(lines, device_id, _RAID_MODULE, enable)
    if enable and mode:
        lines.append(_format_change(device_id, f"{_RAID_MODULE}.Raid.Mode", mode))
    return TranslateResult(lines=lines)


def _translate_gems(device_id: str, payload: Any) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    if len(pl) == 1:
        lines: list[str] = []
        _emit_scheduler(lines, device_id, _GEMS_MODULE, _as_bool(pl[0]))
        return TranslateResult(lines=lines)
    enable = _as_bool(pl[0])
    name = _as_str(pl[1])
    mode = _as_str(pl[2]) if len(pl) > 2 and pl[2] not in (None, "") else "normal"
    event = DEFAULT_EVENT_ID if re.match(r"^(t|ht|a|b|c|d|sp)\d+$", name, re.I) else None
    lines: list[str] = []
    _emit_campaign(
        lines,
        device_id,
        _GEMS_MODULE,
        enable=enable,
        name=name or None,
        mode=mode,
        event=event,
    )
    return TranslateResult(lines=lines)


def _translate_special(device_id: str, payload: Any) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    enable = _as_bool(pl[0])
    mode = _as_str(pl[1]) if len(pl) > 1 and pl[1] not in (None, "") else "normal"
    lines: list[str] = []
    _emit_campaign(
        lines,
        device_id,
        _SPECIAL_MODULE,
        enable=enable,
        mode=mode,
    )
    return TranslateResult(lines=lines)


def _translate_opsi_batch(device_id: str, enable: bool) -> TranslateResult:
    lines = [_format_change(device_id, p, enable) for p in _OPSI_ENABLE_PATHS]
    return TranslateResult(lines=lines)


def _translate_stop_time(device_id: str, payload: Any) -> TranslateResult:
    if not isinstance(payload, list):
        return TranslateResult(error="停止运行 载荷须为数组")
    reason = stop_time_reject_reason(payload)
    if reason:
        return TranslateResult(error=reason)
    ts = datetime.now(timezone.utc).isoformat()
    return TranslateResult(
        scheduled=[
            {
                "kind": "stop_time",
                "device_id": device_id,
                "payload": payload,
                "updated_at": ts,
                "state": {},
            }
        ]
    )


def _translate_userdata_bool(
    device_id: str,
    field: str,
    payload: Any,
) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    lines = [format_userdata_line(device_id, field, _as_bool(pl[0]))]
    return TranslateResult(lines=lines)


def _translate_auto_chouka(device_id: str, payload: Any) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    lines = [format_userdata_line(device_id, "AutoChouKa", _as_bool(pl[0]))]
    if len(pl) > 1 and pl[1] is not None:
        lines.append(format_userdata_line(device_id, "AutoChouKaUsingRubik", int(pl[1])))
    if len(pl) > 2 and pl[2] is not None:
        lines.append(format_userdata_line(device_id, "AutoChouKaPool", _as_str(pl[2])))
    if len(pl) > 3 and pl[3] is not None:
        lines.append(format_userdata_line(device_id, "AutoChouKaTimes", int(pl[3])))
    return TranslateResult(lines=lines)


def _translate_auto_getexp(device_id: str, payload: Any) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    lines = [format_userdata_line(device_id, "AutoGetEXP", _as_bool(pl[0]))]
    if len(pl) > 1 and pl[1] is not None:
        lines.append(format_userdata_line(device_id, "AutoGetEXPReserveBooks", int(pl[1])))
    return TranslateResult(lines=lines)


def _translate_auto_break(device_id: str, payload: Any) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    lines = [format_userdata_line(device_id, "AutoBreakthrough", _as_bool(pl[0]))]
    if len(pl) > 1 and pl[1] is not None:
        lines.append(format_userdata_line(device_id, "StarChoose", int(pl[1])))
    return TranslateResult(lines=lines)


def _translate_assemble(
    device_id: str,
    payload: Any,
    *,
    main: bool,
) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    field = "AutoAssembleTeamMain" if main else "AutoAssembleTeamEvent"
    rule_field = "AutoAssembleTeamMainRule" if main else "AutoAssembleTeamEventRule"
    time_field = "AutoAssembleTeamMainTime" if main else "AutoAssembleTeamEventTime"
    lines = [format_userdata_line(device_id, field, _as_bool(pl[0]))]
    if len(pl) > 1 and pl[1] not in (None, ""):
        lines.append(format_userdata_line(device_id, rule_field, _as_str(pl[1])))
    if len(pl) > 2 and pl[2] is not None:
        lines.append(format_userdata_line(device_id, time_field, int(pl[2])))
    return TranslateResult(lines=lines)


def _translate_plan(device_id: str, payload: Any) -> TranslateResult:
    pl = _payload_list(payload)
    if not pl:
        return TranslateResult(error="载荷为空")
    lines = [format_userdata_line(device_id, "PlanEnabled", _as_bool(pl[0]))]
    if len(pl) > 1 and pl[1] not in (None, ""):
        lines.append(format_userdata_line(device_id, "PlanMode", _as_str(pl[1])))
    if len(pl) > 2 and pl[2] not in (None, ""):
        lines.append(format_userdata_line(device_id, "PlanSchedule", _as_str(pl[2])))
    return TranslateResult(lines=lines)


def translate_semantic(
    device_id: str,
    name: str,
    payload: Any,
) -> TranslateResult:
    """将「指令名 + 数组载荷」转译为可执行的 change/userdata 行或定时任务。"""
    name = _norm_name(name)

    if name in _MAIN_MODULES:
        mod = _MAIN_MODULES[name]
        return _translate_main_event(
            device_id,
            mod,
            payload,
            default_mode="normal",
            default_fleet="3a1n",
        )

    if name in _EVENT_MODULES:
        mod = _EVENT_MODULES[name]
        return _translate_main_event(
            device_id,
            mod,
            payload,
            default_name=DEFAULT_EVENT_STAGE,
            default_mode="normal",
            default_fleet="6a1n",
            default_event=DEFAULT_EVENT_ID,
            event_layout=True,
        )

    if name == "共斗活动":
        return _translate_raid(device_id, payload)

    if name == "特殊活动":
        return _translate_special(device_id, payload)

    if name == "紧急委托":
        pl = _payload_list(payload)
        return _translate_gems(
            device_id,
            payload,
        ) if pl else TranslateResult(error="载荷为空")

    if name in ("大世界功能开", "大世界功能关"):
        enable = name == "大世界功能开"
        return _translate_opsi_batch(device_id, enable)

    if name in ("停止运行", "StopTime"):
        return _translate_stop_time(device_id, payload)

    if name in ("自动配队主线",):
        return _translate_assemble(device_id, payload, main=True)

    if name in ("自动配队活动",):
        return _translate_assemble(device_id, payload, main=False)

    if name in ("自动抽卡",):
        return _translate_auto_chouka(device_id, payload)

    if name in ("自动突破",):
        return _translate_auto_break(device_id, payload)

    if name in ("自动吃书",):
        return _translate_auto_getexp(device_id, payload)

    if name in ("自动兑换活动商店",):
        return _translate_userdata_bool(device_id, "AutoEventShop", payload)

    if name in ("账号规划", "PlanEnabled"):
        return _translate_plan(device_id, payload)

    if name in ("账号分析", "AccountAnalysis"):
        return TranslateResult(error="账号分析由 ProAlas 即时处理，不进入 CPIA 队列")

    return TranslateResult(error=f"未知语义指令「{name}」")
