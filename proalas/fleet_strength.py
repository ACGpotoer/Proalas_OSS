"""UserData.FleetStrength 结构：六队实力预览（ProAlas OCR 回写至 config ProalasData，DAP 只读展示）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _empty_ship(slot: int) -> dict[str, Any]:
    return {
        "slot": slot,
        "name": "",
        "endurance": None,
        "consumption": None,
        "power": None,
        "empty": True,
    }


def _empty_team(team: int) -> dict[str, Any]:
    return {
        "team": team,
        "backPower": 0,
        "frontPower": 0,
        "ships": [_empty_ship(i) for i in range(1, 7)],
    }


def default_fleet_strength() -> dict[str, Any]:
    return {
        "updatedAt": None,
        "teams": [_empty_team(i) for i in range(1, 7)],
    }


def _coerce_int(val: Any, default: int = 0) -> int:
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _coerce_opt_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def normalize_fleet_strength(raw: Any) -> dict[str, Any]:
    """合并缺省结构，保证 6 队 × 6 槽。"""
    out = default_fleet_strength()
    if not isinstance(raw, dict):
        return out

    if raw.get("updatedAt") is not None:
        out["updatedAt"] = str(raw["updatedAt"])

    teams_raw = raw.get("teams")
    if not isinstance(teams_raw, list):
        return out

    teams_by_no: dict[int, dict[str, Any]] = {}
    for item in teams_raw:
        if not isinstance(item, dict):
            continue
        team_no = _coerce_int(item.get("team"), 0)
        if not 1 <= team_no <= 6:
            continue
        base = _empty_team(team_no)
        base["backPower"] = _coerce_int(item.get("backPower"), 0)
        base["frontPower"] = _coerce_int(item.get("frontPower"), 0)

        ships_raw = item.get("ships")
        ships_by_slot: dict[int, dict[str, Any]] = {}
        if isinstance(ships_raw, list):
            for ship in ships_raw:
                if not isinstance(ship, dict):
                    continue
                slot = _coerce_int(ship.get("slot"), 0)
                if not 1 <= slot <= 6:
                    continue
                ships_by_slot[slot] = {
                    "slot": slot,
                    "name": str(ship.get("name") or "").strip(),
                    "endurance": _coerce_opt_int(ship.get("endurance")),
                    "consumption": _coerce_opt_int(ship.get("consumption")),
                    "power": _coerce_opt_int(ship.get("power")),
                    "empty": bool(ship.get("empty", not str(ship.get("name") or "").strip())),
                }

        base["ships"] = [
            ships_by_slot.get(i, _empty_ship(i)) for i in range(1, 7)
        ]
        teams_by_no[team_no] = base

    out["teams"] = [teams_by_no.get(i, _empty_team(i)) for i in range(1, 7)]
    return out


def fleet_strength_for_device(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return default_fleet_strength()
    return normalize_fleet_strength(row.get("FleetStrength"))


def fleet_strength_from_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """从 config ProalasData.FleetStrength 或兼容旧 FleetStrength 顶层字段。"""
    if not isinstance(config, dict):
        return default_fleet_strength()
    proalas = config.get("ProalasData")
    if isinstance(proalas, dict) and isinstance(proalas.get("FleetStrength"), dict):
        return normalize_fleet_strength(proalas["FleetStrength"])
    return normalize_fleet_strength(config.get("FleetStrength"))
