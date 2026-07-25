# -*- coding: utf-8 -*-
"""ProAlas 设备截图目录（./img/{config_name}/）。"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from module.base.utils import save_image

ALAS_ROOT = Path(__file__).resolve().parents[2]
IMG_ROOT = ALAS_ROOT / 'img'
LATEST_NAME = 'latest.png'


def img_root() -> Path:
    IMG_ROOT.mkdir(parents=True, exist_ok=True)
    return IMG_ROOT


def device_img_dir(config_name: str) -> Path:
    name = str(config_name or 'alas').strip() or 'alas'
    path = img_root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp_name(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime('%Y-%m-%d_%H-%M-%S') + '.png'


def list_screenshot_files(config_name: str, limit: int = 10) -> list[str]:
    """Return newest timestamped PNG names (exclude latest.png)."""
    directory = device_img_dir(config_name)
    files = [
        p.name
        for p in directory.glob('*.png')
        if p.is_file() and p.name != LATEST_NAME
    ]
    files.sort(reverse=True)
    if limit > 0:
        files = files[:limit]
    return files


def trim_screenshots(config_name: str, keep: int = 10) -> None:
    if keep <= 0:
        return
    directory = device_img_dir(config_name)
    files = [
        p
        for p in directory.glob('*.png')
        if p.is_file() and p.name != LATEST_NAME
    ]
    files.sort(key=lambda p: p.name, reverse=True)
    for path in files[keep:]:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass


def save_device_screenshot(image, config_name: str, keep: int = 10) -> str:
    """
    Save screenshot to img/{config_name}/{timestamp}.png and refresh latest.png.
    Returns saved timestamp filename.
    """
    directory = device_img_dir(config_name)
    filename = _timestamp_name()
    target = directory / filename
    save_image(image, str(target))
    latest = directory / LATEST_NAME
    try:
        shutil.copy2(target, latest)
    except OSError:
        save_image(image, str(latest))
    trim_screenshots(config_name, keep=keep)
    return filename


def latest_screenshot_path(config_name: str) -> Path | None:
    latest = device_img_dir(config_name) / LATEST_NAME
    if latest.is_file():
        return latest
    files = list_screenshot_files(config_name, limit=1)
    if not files:
        return None
    path = device_img_dir(config_name) / files[0]
    return path if path.is_file() else None


def img_url(config_name: str, filename: str) -> str:
    name = str(config_name or 'alas').strip() or 'alas'
    return f'/img/{name}/{filename}'
