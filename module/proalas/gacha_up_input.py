# -*- coding: utf-8 -*-
"""中文船名输入：MuMuManager / 主机剪贴板+粘贴 / xwkeyboard 多路 fallback。"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from module.GachaUp import assets as A
from module.logger import logger

InputFn = Callable[[Any, str], bool]


def _device_serial(device) -> str:
    return str(getattr(device, 'serial', '') or '').strip()


def _device_port(device) -> str:
    serial = _device_serial(device)
    if ':' in serial:
        return serial.rsplit(':', 1)[-1]
    return serial


def _device_config_name(device) -> str:
    cfg = getattr(device, 'config', None)
    if cfg is None:
        return ''
    return str(getattr(cfg, 'config_name', '') or '').strip()


def resolve_mumu_index(device) -> str | None:
    """adb 端口反查 → devices.yaml → 环境变量 GACHA_UP_MUMU_INDEX。"""
    env = os.environ.get('GACHA_UP_MUMU_INDEX', '').strip()
    if env:
        return env

    port = _device_port(device)
    if port:
        try:
            from mumucontrol.drivers.mumu import MuMuControl

            idx = MuMuControl().find_index_by_adb_port(port)
            if idx:
                logger.info('GachaUp resolved MuMu index=%s from port=%s', idx, port)
                return idx
        except Exception as e:
            logger.warning('GachaUp find_index_by_adb_port failed: %s', e)

    config_name = _device_config_name(device)
    yaml_path = Path(__file__).resolve().parents[2] / 'mumucontrol' / 'devices.yaml'
    if yaml_path.is_file() and config_name:
        try:
            import yaml

            raw = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
            devices = (raw or {}).get('devices') or {}
            spec = devices.get(config_name)
            if isinstance(spec, dict):
                idx = str(spec.get('index') or '').strip()
                if idx:
                    return idx
        except Exception as e:
            logger.warning('GachaUp devices.yaml lookup failed: %s', e)
    return None


def set_host_clipboard(text: str, *, retries: int | None = None) -> bool:
    """Windows 优先 ctypes 写剪贴板；失败时重试（避免连续两艘船时 OpenClipboard 被占用）。"""
    text = str(text or '')
    if not text:
        return False

    retries = A._CLIPBOARD_RETRY if retries is None else max(1, int(retries))
    for attempt in range(1, retries + 1):
        if _set_host_clipboard_once(text):
            return True
        if attempt < retries:
            logger.info('GachaUp clipboard retry %s/%s', attempt, retries)
            time.sleep(A._STEP_PAUSE)
    return False


def _set_host_clipboard_once(text: str) -> bool:
    if os.name == 'nt':
        try:
            import ctypes

            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    payload = text.encode('utf-16-le') + b'\x00\x00'
                    h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
                    if h_global:
                        p_global = kernel32.GlobalLock(h_global)
                        ctypes.memmove(p_global, payload, len(payload))
                        kernel32.GlobalUnlock(h_global)
                        if user32.SetClipboardData(CF_UNICODETEXT, h_global):
                            return True
                        kernel32.GlobalFree(h_global)
                finally:
                    user32.CloseClipboard()
        except Exception as e:
            logger.debug('GachaUp win32 clipboard failed: %s', e)

        try:
            import win32clipboard  # type: ignore

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        pass

    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        return False


def paste_via_adb(device, *, sleep_after: float | None = None) -> bool:
    """模拟器内粘贴（MuMu 共享剪贴板 + KEYCODE_PASTE）。"""
    wait = A._AFTER_INPUT_PASTE if sleep_after is None else float(sleep_after)
    try:
        device.adb_shell(['input', 'keyevent', str(A.KEYCODE_PASTE)])
        time.sleep(wait)
        return True
    except Exception as e:
        logger.warning('GachaUp adb paste keyevent failed: %s', e)
        return False


def paste_via_win32_ctrl_v(*, sleep_after: float = 0.35) -> bool:
    """向当前前台窗口发送 Ctrl+V（与手动粘贴一致，需 MuMu 窗口获焦）。"""
    if os.name != 'nt':
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_V = 0x56
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(sleep_after)
        return True
    except Exception as e:
        logger.warning('GachaUp win32 Ctrl+V failed: %s', e)
        return False


def _focus_search_field(device) -> None:
    """再次点搜索框，确保输入焦点在船坞检索栏。"""
    try:
        if A.DOCK_NAV_CLICKS:
            x, y = A.CLICK_SEARCH_INPUT
            device.click_adb(x, y)
            device.sleep(A._STEP_PAUSE)
    except Exception as e:
        logger.debug('GachaUp focus search field skipped: %s', e)


def input_via_mumu_manager(device, text: str) -> bool:
    index = resolve_mumu_index(device)
    if not index:
        logger.warning('GachaUp MuMu index unresolved serial=%s', _device_serial(device))
        return False
    try:
        from mumucontrol.drivers.mumu import MuMuControl

        return MuMuControl().adb_input_text(index, text)
    except Exception as e:
        logger.warning('GachaUp MuMuManager input_text failed: %s', e)
        return False


def input_via_host_clipboard_adb(device, text: str) -> bool:
    if not set_host_clipboard(text):
        logger.warning('GachaUp host clipboard set failed')
        return False
    time.sleep(A._STEP_PAUSE)
    return paste_via_adb(device)


def input_via_host_clipboard_ctrl_v(device, text: str) -> bool:
    if not set_host_clipboard(text):
        logger.warning('GachaUp host clipboard set failed')
        return False
    time.sleep(A._STEP_PAUSE)
    if paste_via_adb(device):
        return True
    logger.info('GachaUp adb paste miss, trying win32 Ctrl+V')
    time.sleep(A._STEP_PAUSE)
    return paste_via_win32_ctrl_v(sleep_after=A._AFTER_INPUT_PASTE)


def input_via_xwkeyboard(device, text: str) -> bool:
    serial = _device_serial(device)
    if not serial:
        return False
    ime_id = 'com.android.xwkeyboard/.XwIME'
    try:
        for args in (
            ['adb', '-s', serial, 'shell', 'ime', 'enable', ime_id],
            ['adb', '-s', serial, 'shell', 'ime', 'set', ime_id],
        ):
            r = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=15,
            )
            if r.returncode != 0:
                err = (r.stderr or r.stdout or '').strip()
                logger.warning('GachaUp xwkeyboard ime switch failed: %s', err)
                return False
        time.sleep(0.25)
        r = subprocess.run(
            ['adb', '-s', serial, 'shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15,
        )
        err = (r.stderr or r.stdout or '').strip()
        if r.returncode != 0:
            logger.warning('GachaUp ADB_INPUT_TEXT failed rc=%s err=%s', r.returncode, err)
            return False
        logger.info('GachaUp ADB_INPUT_TEXT sent')
        time.sleep(0.6)
        return True
    except Exception as e:
        logger.warning('GachaUp xwkeyboard input failed: %s', e)
        return False


_INPUT_METHODS: tuple[tuple[str, InputFn], ...] = (
    ('host_clipboard_adb', input_via_host_clipboard_adb),
    ('host_clipboard_ctrl_v', input_via_host_clipboard_ctrl_v),
    ('mumu_manager', input_via_mumu_manager),
    ('xwkeyboard', input_via_xwkeyboard),
)


def input_text_zh(device, text: str, *, config=None) -> bool:
    text = str(text or '').strip()
    if not text:
        return False

    if config is not None and not getattr(device, 'config', None):
        device.config = config

    _focus_search_field(device)
    time.sleep(A._AFTER_INPUT_FOCUS)

    for name, fn in _INPUT_METHODS:
        logger.info('GachaUp input try method=%s text=%r', name, text)
        try:
            if fn(device, text):
                logger.info('GachaUp input ok method=%s text=%r', name, text)
                time.sleep(A._AFTER_INPUT_PASTE)
                return True
        except Exception as e:
            logger.warning('GachaUp input method=%s error: %s', name, e)
        time.sleep(A._STEP_PAUSE)
    logger.warning('GachaUp all input methods failed for %r', text)
    return False
