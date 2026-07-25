"""读取设备运行截图：Alas ProalasScreenMonitor（img/{device}/）与 ProAlas data/img/。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_ALAS_LATEST = "latest.png"


@dataclass(frozen=True)
class ScreenShotInfo:
    path: Path
    filename: str
    shot_label: str
    source: str  # alas | proalas
    mtime: float


def screenshot_root_from_user_data(user_data_path: str | Path) -> Path:
    """与 ProAlas `core.root_event._take_device_screenshot` 一致：UserData 同级的 img/。"""
    return Path(user_data_path).resolve().parent / "img"


def alas_screenshot_dir(device_id: str, config_dir: str | Path) -> Path:
    """Alas `module/proalas/screen_paths.py` → {ALAS_ROOT}/img/{device_id}/。"""
    return Path(config_dir).resolve().parent / "img" / device_id


def resolve_screenshot_root(config: dict) -> Path:
    explicit = (config.get("DEVICE_SCREENSHOT_ROOT") or "").strip()
    if explicit:
        return Path(explicit).resolve()
    cfg_dir = (config.get("CONFIG_DIR") or "").strip()
    if cfg_dir:
        parent = Path(cfg_dir).resolve().parent
        img = parent / "img"
        if img.is_dir() or not (parent / "data" / "img").is_dir():
            return img
        return parent / "data" / "img"
    return screenshot_root_from_user_data(config.get("USER_DATA_PATH") or "")


def _file_date(name: str) -> Optional[str]:
    m = _DATE_PREFIX.match(name)
    return m.group(1) if m else None


def _format_shot_label(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return path.stem


def _pick_newest(paths: list[Path]) -> Optional[Path]:
    if not paths:
        return None
    return max(paths, key=lambda p: p.stat().st_mtime)


def _find_in_alas_dir(device_id: str, config_dir: str | Path) -> Optional[ScreenShotInfo]:
    img_dir = alas_screenshot_dir(device_id, config_dir)
    if not img_dir.is_dir():
        return None

    latest = img_dir / _ALAS_LATEST
    if latest.is_file():
        return ScreenShotInfo(
            path=latest,
            filename=_ALAS_LATEST,
            shot_label=_format_shot_label(latest),
            source="alas",
            mtime=latest.stat().st_mtime,
        )

    files = [p for p in img_dir.glob("*.png") if p.is_file() and p.name != _ALAS_LATEST]
    best = _pick_newest(files)
    if not best:
        return None
    return ScreenShotInfo(
        path=best,
        filename=best.name,
        shot_label=_format_shot_label(best),
        source="alas",
        mtime=best.stat().st_mtime,
    )


def find_latest_device_screenshot(
    device_id: str,
    root: str | Path,
) -> Optional[Path]:
    """
    ProAlas 悬浮窗目录：取该设备「最新自然日」下 mtime 最新的一张 PNG。
    文件名格式：YYYY-MM-DD-HH-MM-SS-ffffff_{device_id}.png
    """
    img_dir = Path(root) / device_id
    if not img_dir.is_dir():
        return None
    files = [p for p in img_dir.glob("*.png") if p.is_file()]
    if not files:
        return None

    by_date: dict[str, list[Path]] = {}
    fallback: list[Path] = []
    for p in files:
        d = _file_date(p.name)
        if d:
            by_date.setdefault(d, []).append(p)
        else:
            fallback.append(p)

    if by_date:
        latest_date = max(by_date)
        pool = by_date[latest_date]
    else:
        pool = fallback

    return _pick_newest(pool)


def _find_in_proalas_root(device_id: str, config: dict) -> Optional[ScreenShotInfo]:
    root = resolve_screenshot_root(config)
    path = find_latest_device_screenshot(device_id, root)
    if not path:
        return None
    return ScreenShotInfo(
        path=path,
        filename=path.name,
        shot_label=_format_shot_label(path),
        source="proalas",
        mtime=path.stat().st_mtime,
    )


def find_screen_monitor_shot(device_id: str, app_config: dict) -> Optional[ScreenShotInfo]:
    """优先 Alas 截图监控目录，其次 ProAlas data/img。"""
    config_dir = (app_config.get("CONFIG_DIR") or "").strip()
    candidates: list[ScreenShotInfo] = []
    if config_dir:
        alas = _find_in_alas_dir(device_id, config_dir)
        if alas:
            candidates.append(alas)
    proalas = _find_in_proalas_root(device_id, app_config)
    if proalas:
        candidates.append(proalas)
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.mtime)


def image_url_for_shot(device_id: str, shot: ScreenShotInfo) -> str:
    """走 DAP 本地路由，不依赖 Alas WebUI /img 代理（上游未启动时避免 502）。"""
    return f"/app/pro/screen-shot/{device_id}/{shot.filename}"


def resolve_local_shot_path(
    device_id: str,
    filename: str,
    app_config: dict,
) -> Optional[Path]:
    """校验并返回本地 PNG 路径：先 Alas img/{device}，再 ProAlas data/img。"""
    name = Path(filename).name
    if not name or name != filename or ".." in filename:
        return None

    config_dir = (app_config.get("CONFIG_DIR") or "").strip()
    if config_dir:
        alas_dir = alas_screenshot_dir(device_id, config_dir)
        try:
            alas_resolved = alas_dir.resolve()
            alas_path = (alas_dir / name).resolve()
            if str(alas_path).startswith(str(alas_resolved)) and alas_path.is_file():
                return alas_path
        except OSError:
            pass

    root = resolve_screenshot_root(app_config)
    path = (root / device_id / name).resolve()
    try:
        root_resolved = (root / device_id).resolve()
    except OSError:
        return None
    if not str(path).startswith(str(root_resolved)):
        return None
    return path if path.is_file() else None
