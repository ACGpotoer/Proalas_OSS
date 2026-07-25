"""校验 change 指令中的 config 路径是否存在于该设备的 Alas JSON。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ProAlas UserData 语义指令（预提示词 21-31 行）：无 Alas config 路径，写入 special_commands.pending
# 规范名为 UserData.json 字段名；由 ProAlas 转译/消费（非 CPIA）
_SPECIAL_ALIAS_TO_CANONICAL: dict[str, str] = {
    "AutoAssembleTeamMain": "AutoAssembleTeamMain",
    "AutoAssembleTeamEvent": "AutoAssembleTeamEvent",
    "AutoChouKa": "AutoChouKa",
    "AutoBreakthrough": "AutoBreakthrough",
    "AutoGetEXP": "AutoGetEXP",
    "AutoEventShop": "AutoEventShop",
    "PlanEnabled": "PlanEnabled",
    "AccountAnalysis": "AccountAnalysis",
    "StopTime": "StopTime",
    "停止运行": "StopTime",
    "自动配队主线": "AutoAssembleTeamMain",
    "自动配队活动": "AutoAssembleTeamEvent",
    "自动抽卡": "AutoChouKa",
    "打开自动抽卡": "AutoChouKa",
    "自动突破": "AutoBreakthrough",
    "自动吃书": "AutoGetEXP",
    "打开自动吃书": "AutoGetEXP",
    "自动兑换活动商店": "AutoEventShop",
    "打开自动兑换商店": "AutoEventShop",
    "打开自动突破": "AutoBreakthrough",
    "账号规划": "PlanEnabled",
    "账号分析": "AccountAnalysis",
}


def _normalize_special_token(name: str) -> str:
    s = name.strip()
    if s.isascii():
        return s.lower()
    return s


def resolve_special_command_name(name: str) -> str | None:
    """将指令名（中文或英文）解析为规范名；未知则 None。"""
    key = _normalize_special_token(name)
    if key in _SPECIAL_ALIAS_TO_CANONICAL:
        return _SPECIAL_ALIAS_TO_CANONICAL[key]
    # 原始中文未 lower
    if name.strip() in _SPECIAL_ALIAS_TO_CANONICAL:
        return _SPECIAL_ALIAS_TO_CANONICAL[name.strip()]
    return None


def load_device_config(config_dir: str, device_id: str) -> dict | None:
    p = Path(config_dir).expanduser() / f"{device_id}.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def parse_change_command(cmd: str) -> tuple[str, str, str] | None:
    """
    解析形如：change <device_id> <Module>.<Sub...>.<Key> <value>
    约定路径段不含空格；value 为最后一个以空白分隔的词（与预提示词示例一致）。
    """
    parts = cmd.strip().split()
    if len(parts) < 4:
        return None
    if parts[0].lower() != "change":
        return None
    dev = parts[1]
    value = parts[-1]
    middle = parts[2:-1]
    if not middle:
        return None
    path = ".".join(middle)
    if not re.match(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$", path):
        return None
    return dev, path, value


def parse_change_tokens(cmd: str) -> tuple[str, str, str] | None:
    """解析 change 行：返回 (device_id, path_or_instruction_name, value)；path 可含点或为单词。"""
    parts = cmd.strip().split()
    if len(parts) < 4:
        return None
    if parts[0].lower() != "change":
        return None
    dev = parts[1]
    value = parts[-1]
    middle = parts[2:-1]
    if not middle:
        return None
    name = ".".join(middle)
    return dev, name, value


def format_special_change_line(device_id: str, canonical: str, value: str) -> str:
    return f"change {device_id} {canonical} {value}"


def split_normalized_special_change(cmd: str) -> tuple[str, str, str] | None:
    """已规范化的扩展 change 行 → (device_id, canonical_name, value)；指令名单段、值为最后一词。"""
    parts = cmd.strip().split()
    if len(parts) < 4 or parts[0].lower() != "change":
        return None
    dev = parts[1]
    value = parts[-1]
    middle = parts[2:-1]
    if len(middle) != 1:
        return None
    return dev, middle[0], value


def path_exists_in_config(cfg: dict, dotted: str) -> bool:
    keys = dotted.split(".")
    cur: Any = cfg
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return False
        cur = cur[k]
    return True


def validate_change_line(cmd: str, session_device_id: str, cfg: dict | None) -> tuple[bool, str | None]:
    if cfg is None:
        return True, None
    p = parse_change_command(cmd)
    if p is None:
        return True, None
    dev, path, _val = p
    if dev != session_device_id:
        return False, f"设备号不一致：指令为 {dev}，当前为 {session_device_id}"
    if not path_exists_in_config(cfg, path):
        return (
            False,
            f"config 中不存在路径「{path}」。主线关卡须用 Main.Campaign.Name / Main.Campaign.Mode，"
            "禁止使用不存在的 Main.Chapter.* 等键名。",
        )
    return True, None


def filter_commands_for_device(
    commands: list[str],
    *,
    device_id: str,
    config_dir: str,
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """返回 (alas 通过的 change 列表, 扩展功能 special 列表, [(指令, 原因), ...])。

    扩展功能：change <设备> <UserData字段名> <值>，字段名见提示词及其路径对照键值.txt ProAlas 段，
    不落 Alas config 校验，写入 commands.json 的 special_commands.pending（由 ProAlas 消费）。
    """
    cfg = load_device_config(config_dir, device_id)
    ok_alas: list[str] = []
    ok_special: list[str] = []
    bad: list[tuple[str, str]] = []
    for c in commands:
        stripped = c.strip()
        if not stripped.lower().startswith("change "):
            ok_alas.append(c)
            continue
        tok = parse_change_tokens(stripped)
        if tok is None:
            bad.append((c, "无法解析的 change 行（至少需要 change 设备 名 值）。"))
            continue
        dev, path_or_name, val = tok
        if dev != device_id:
            bad.append((c, f"设备号不一致：指令为 {dev}，当前为 {device_id}"))
            continue
        canon = resolve_special_command_name(path_or_name)
        if canon is not None:
            ok_special.append(format_special_change_line(device_id, canon, val))
            continue
        if "." not in path_or_name:
            bad.append(
                (
                    c,
                    "非 Alas 点分路径且非已登记的 ProAlas/UserData 指令名；"
                    "请使用预提示词指令集或对照表中的中文名，"
                    "或使用 config 中存在的 Module.Sub.Key 路径。",
                )
            )
            continue
        good, err = validate_change_line(stripped, device_id, cfg)
        if good:
            ok_alas.append(c)
        else:
            bad.append((c, err or "校验未通过"))
    return ok_alas, ok_special, bad
