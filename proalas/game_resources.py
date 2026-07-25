"""UserData.GameResource → DAP 资源面板字段对齐。"""
from __future__ import annotations

from typing import Any

# ProAlas log_resource_sync._RESOURCE_KEYS 写入键 + 扩展只读键
RESOURCE_LABELS: dict[str, str] = {
    "oil": "石油",
    "money": "物资",
    "Rmb": "钻石",
    "ExpBook": "教材",
    "OpsiYellow": "黄币",
    "OpsiPurple": "紫币",
    "OpsiWhite": "白票",
    "Act-Pt": "活动PT",
    "cube": "魔方",
    "BoatDock": "船坞情况",
    "BoatRate": "收藏率",
    "BoatMax": "船坞上限",
}


def format_boat_dock_display(raw: Any) -> str:
    """GameResource.BoatDock，如 790/794。"""
    text = str(raw or "").strip()
    return text or "—"


def format_boat_rate_display(raw: Any) -> str:
    """GameResource.BoatRate：比例 0.802 → 80.2%。"""
    if raw is None or raw == "":
        return "—"
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return str(raw)
    if rate <= 0:
        return "0%"
    # 兼容旧数据：若已是百分数（如 98、80.2），不再乘 100
    if rate > 1.5:
        pct = round(rate * 10) / 10.0
    else:
        pct = round(rate * 1000) / 10.0
    if pct == int(pct):
        return f"{int(pct)}%"
    return f"{pct:.1f}%"


def normalize_game_resource(raw: dict[str, Any] | None) -> dict[str, Any]:
    """合并默认值，供模板只读展示。"""
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {
        "oil": int(src.get("oil") or 0),
        "money": int(src.get("money") or 0),
        "Rmb": int(src.get("Rmb") or 0),
        "ExpBook": int(src.get("ExpBook") or 0),
        "OpsiYellow": int(src.get("OpsiYellow") or 0),
        "OpsiPurple": int(src.get("OpsiPurple") or 0),
        "OpsiWhite": int(src.get("OpsiWhite") or 0),
        "Act-Pt": int(src.get("Act-Pt") or 0),
        "cube": int(src.get("cube") or 0),
        "BoatDock": format_boat_dock_display(src.get("BoatDock")),
        "BoatRate": format_boat_rate_display(src.get("BoatRate")),
        "BoatMax": int(src.get("BoatMax") or 0),
        "syncedAt": src.get("syncedAt") or "",
        "cubeSyncedAt": src.get("cubeSyncedAt") or "",
        "boatSyncedAt": src.get("boatSyncedAt") or "",
    }
    return out


def resource_tiles(gr: dict[str, Any]) -> list[dict[str, Any]]:
    """主面板展示顺序（与更新公告：物资、石油、活动Pt 等）。"""
    order = (
        "oil",
        "money",
        "cube",
        "BoatDock",
        "BoatRate",
        "Act-Pt",
        "Rmb",
        "ExpBook",
        "OpsiYellow",
        "OpsiPurple",
        "OpsiWhite",
    )
    tiles = []
    for key in order:
        tiles.append(
            {
                "key": key,
                "label": RESOURCE_LABELS.get(key, key),
                "value": gr.get(key, 0),
            }
        )
    return tiles
